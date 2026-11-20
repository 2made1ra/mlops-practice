"""Run one CIFAR classification experiment from its JSON config."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import tempfile
from time import perf_counter
from typing import NotRequired, TypedDict

from botocore.exceptions import ClientError
from dotenv import load_dotenv
import mlflow
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader

from mlops_practice.publish import git
from mlops_practice.s3 import make_client
from mlops_practice.training_data import DatasetSplits, load_datasets


class DataConfig(TypedDict):
    s3_path: str
    max_train_samples: NotRequired[int | None]


class ModelParams(TypedDict):
    channels: NotRequired[list[int]]


class ModelConfig(TypedDict):
    type: str
    params: NotRequired[ModelParams]


class TrainConfig(TypedDict):
    epochs: int
    batch_size: int
    lr: float


class Config(TypedDict):
    experiment_name: str
    run_name: str
    seed: int
    data: DataConfig
    model: ModelConfig
    train: TrainConfig


def read_config(path: Path) -> Config:
    config: Config = json.loads(path.read_text(encoding="utf-8"))
    for name in (config["experiment_name"], config["run_name"]):
        if not name.strip() or "/" in name or name in (".", ".."):
            raise ValueError(f"Expected a single S3 path component for the name, got {name!r}")
    train = config["train"]
    if train["epochs"] < 1 or train["batch_size"] < 1:
        raise ValueError("train.epochs and train.batch_size must be positive")
    if not math.isfinite(train["lr"]) or train["lr"] <= 0:
        raise ValueError("train.lr must be finite and positive")
    return config


def make_model(config: ModelConfig, classes: int) -> nn.Sequential:
    if config["type"] == "linear":
        return nn.Sequential(nn.Flatten(), nn.Linear(3 * 32 * 32, classes))
    if config["type"] != "simple_cnn":
        raise ValueError(f"Unknown model.type: {config['type']}")
    channels = config.get("params", ModelParams()).get("channels", [32, 64])
    if len(channels) not in (2, 3) or min(channels) < 1:
        raise ValueError("simple_cnn requires two or three positive channel counts")

    layers: list[nn.Module] = []
    inputs, side = 3, 32
    for outputs in channels:
        layers.extend([nn.Conv2d(inputs, outputs, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2)])
        inputs, side = outputs, side // 2
    return nn.Sequential(*layers, nn.Flatten(), nn.Linear(inputs * side * side, classes))


def evaluate(
    model: nn.Module, loader: DataLoader[tuple[Tensor, Tensor]], classes: int
) -> tuple[dict[str, float], Tensor]:
    model.eval()
    matrix = torch.zeros((classes, classes), dtype=torch.long)
    total_loss = 0.0
    with torch.inference_mode():
        for inputs, targets in loader:
            logits = model(inputs)
            total_loss += nn.functional.cross_entropy(logits, targets, reduction="sum").item()
            pairs = targets * classes + logits.argmax(dim=1)
            matrix += torch.bincount(pairs, minlength=classes**2).reshape(classes, classes)

    count = matrix.sum().item()
    if not count:
        raise ValueError("Cannot evaluate an empty split")
    correct = matrix.diag()
    # Each denominator is the number of true examples plus the number of predictions.
    f1 = (2 * correct) / (matrix.sum(dim=1) + matrix.sum(dim=0)).clamp_min(1)
    scores = {
        "loss": total_loss / count,
        "accuracy": correct.sum().item() / count,
        "macro_f1": f1.mean().item(),
    }
    return scores, matrix


def fit(
    model: nn.Module, data: DatasetSplits, config: TrainConfig, output: Path
) -> tuple[int, dict[str, float], float]:
    train = DataLoader(data.train, batch_size=config["batch_size"], shuffle=True)
    val = DataLoader(data.val, batch_size=config["batch_size"])
    optimizer = torch.optim.Adam(model.parameters(), lr=config["lr"])
    best_epoch = 0
    best_val: dict[str, float] = {}
    started = perf_counter()
    for epoch in range(1, config["epochs"] + 1):
        model.train()
        for inputs, targets in train:
            optimizer.zero_grad()
            loss = nn.functional.cross_entropy(model(inputs), targets)
            torch.autograd.backward(loss)
            optimizer.step()

        scores, matrix = evaluate(model, val, len(data.class_names))
        if not math.isfinite(scores["loss"]):
            raise ValueError(f"Non-finite validation loss at epoch {epoch}")
        mlflow.log_metrics({f"val_{k}": v for k, v in scores.items()}, step=epoch)
        print(f"Epoch {epoch} val_loss={scores['loss']:.4f} val_accuracy={scores['accuracy']:.4f}")
        if not best_epoch or scores["loss"] < best_val["loss"]:
            best_epoch, best_val = epoch, scores
            torch.save(model.state_dict(), output / "model.pt")
            with (output / "val_confusion.csv").open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["actual / predicted", *data.class_names])
                for label, row in zip(data.class_names, matrix.tolist(), strict=True):
                    writer.writerow([label, *row])
    return best_epoch, best_val, perf_counter() - started


def flatten_params(config: object, prefix: str = "") -> dict[str, str]:
    if isinstance(config, dict) and config:
        params: dict[str, str] = {}
        for key, value in config.items():
            params.update(flatten_params(value, f"{prefix}.{key}" if prefix else key))
        return params
    return {prefix: config if isinstance(config, str) else json.dumps(config)}


def run(config: Config) -> None:
    torch.manual_seed(config["seed"])
    torch.use_deterministic_algorithms(True)
    commit = os.environ.get("GIT_COMMIT") or git("rev-parse", "HEAD").strip()
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment(config["experiment_name"])
    with (
        mlflow.start_run(run_name=config["run_name"]) as active,
        tempfile.TemporaryDirectory() as directory,
    ):
        output = Path(directory)
        client = make_client()
        bucket = os.environ["S3_BUCKET"]
        prefix = f"models/{config['experiment_name']}/{config['run_name']}"
        config_bytes = (json.dumps(config, indent=2) + "\n").encode("utf-8")
        # Claim this name once, even if two trainers start with the same config.
        try:
            client.put_object(
                Bucket=bucket,
                Key=f"{prefix}/config.json",
                Body=config_bytes,
                ContentType="application/json",
                IfNoneMatch="*",
            )
        except ClientError as error:
            if error.response["ResponseMetadata"]["HTTPStatusCode"] in (409, 412):
                raise ValueError(f"{prefix} already exists; use a fresh run_name") from error
            raise
        mlflow.log_params({**flatten_params(config), "git_commit": commit})
        mlflow.set_tag("mlflow.source.git.commit", commit)
        data = load_datasets(
            config["data"]["s3_path"], config["data"].get("max_train_samples"), config["seed"]
        )
        model = make_model(config["model"], len(data.class_names))
        epoch, val, seconds = fit(model, data, config["train"], output)

        model.load_state_dict(
            torch.load(output / "model.pt", map_location="cpu", weights_only=True)
        )
        test_loader = DataLoader(data.test, batch_size=config["train"]["batch_size"])
        test, _ = evaluate(model, test_loader, len(data.class_names))
        mlflow.log_metrics(
            {
                "best_epoch": float(epoch),
                "training_seconds": seconds,
                **{f"best_val_{k}": v for k, v in val.items()},
                **{f"test_{k}": v for k, v in test.items()},
            }
        )

        metrics = {
            "best_epoch": epoch,
            "val": val,
            "test": test,
            "training_seconds": seconds,
            "git_commit": commit,
            "run_id": active.info.run_id,
        }
        (output / "config.json").write_bytes(config_bytes)
        (output / "metrics.json").write_text(
            json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
        )
        mlflow.log_artifacts(directory)
        client.upload_file(str(output / "model.pt"), bucket, f"{prefix}/model.pt")
        client.upload_file(str(output / "metrics.json"), bucket, f"{prefix}/metrics.json")
        print(f"Best epoch {epoch}, val_loss={val['loss']:.4f}; saved to s3://{bucket}/{prefix}/")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    run(read_config(parser.parse_args().config))


if __name__ == "__main__":
    main()
