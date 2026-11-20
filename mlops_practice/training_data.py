"""Load an immutable HW2 dataset version into a shared, local tensor cache."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
import fcntl
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image
import torch
from torch import Tensor
from torch.utils.data import Dataset

from mlops_practice.convert import ImageRecord
from mlops_practice.publish import SPLITS, Manifest
from mlops_practice.s3 import make_client
from mlops_practice.split import load_annotations
from mlops_practice.stats import Stats

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class CifarSplit(Dataset[tuple[Tensor, Tensor]]):
    def __init__(self, directory: Path, split: str, mean: Tensor, std: Tensor) -> None:
        self.images = np.load(directory / f"{split}.npy", mmap_mode="r")
        annotations = load_annotations(directory / f"annotations/{split}.json")
        self.class_names = annotations["classes"]
        self.labels = torch.tensor([row["label"] for row in annotations["images"]])
        self.indices: Sequence[int] = range(len(self.labels))
        self.mean = mean
        self.std = std

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor]:
        i = self.indices[index]
        pixels = torch.tensor(self.images[i], dtype=torch.float32)
        return pixels.div_(255).sub_(self.mean).div_(self.std), self.labels[i]


@dataclass
class DatasetSplits:
    train: CifarSplit
    val: CifarSplit
    test: CifarSplit
    class_names: list[str]


def _read_object(client: S3Client, bucket: str, key: str) -> bytes:
    with closing(client.get_object(Bucket=bucket, Key=key)["Body"]) as stream:
        return stream.read()


def _checked_object(client: S3Client, bucket: str, key: str, digest: str) -> bytes:
    data = _read_object(client, bucket, key)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Checksum mismatch for s3://{bucket}/{key}")
    return data


def _download_split(
    client: S3Client, bucket: str, prefix: str, directory: Path, split: str, expected_size: int
) -> None:
    records = load_annotations(directory / f"annotations/{split}.json")["images"]
    if len(records) != expected_size or not records:
        raise ValueError(f"Unexpected number of images in {split}: {len(records)}")
    images = np.lib.format.open_memmap(
        directory / f"{split}.npy", mode="w+", dtype=np.uint8, shape=(len(records), 3, 32, 32)
    )

    def download(item: tuple[int, ImageRecord]) -> None:
        index, record = item
        raw = _checked_object(client, bucket, f"{prefix}/{record['file_name']}", record["sha256"])
        with Image.open(BytesIO(raw)) as image:
            images[index] = np.asarray(image.convert("RGB")).transpose(2, 0, 1)

    with ThreadPoolExecutor(max_workers=10) as pool:
        for _ in pool.map(download, enumerate(records)):
            pass
    images.flush()


def _cache_version(client: S3Client, bucket: str, prefix: str) -> Path:
    cache = Path(os.environ.get("DATA_CACHE_DIR", "data/processed/cache"))
    source = f"{os.environ['S3_ENDPOINT_URL']}/{bucket}/{prefix}"
    cache_key = hashlib.sha256(source.encode()).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    root = cache / cache_key
    with (cache / f"{cache_key}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if root.is_dir():
            return root
        manifest: Manifest = json.loads(_read_object(client, bucket, f"{prefix}/manifest.json"))
        entries = {entry["path"]: entry for entry in manifest["files"]}
        with TemporaryDirectory(dir=cache) as temp:
            stage = Path(temp) / "dataset"
            (stage / "annotations").mkdir(parents=True)
            for name in ["stats.json", *(f"annotations/{s}.json" for s in SPLITS)]:
                content = _checked_object(
                    client, bucket, f"{prefix}/{name}", entries[name]["sha256"]
                )
                (stage / name).write_bytes(content)
            for split in SPLITS:
                print(f"Downloading {split} from s3://{bucket}/{prefix}", flush=True)
                _download_split(
                    client, bucket, prefix, stage, split, manifest["num_images"][split]
                )
            stage.rename(root)
    return root


def load_datasets(s3_path: str, max_train_samples: int | None, seed: int) -> DatasetSplits:
    """Use the same seeded train subset and complete validation/test splits in every run."""
    client = make_client()
    root = _cache_version(client, os.environ["S3_BUCKET"], s3_path.rstrip("/"))
    stats: Stats = json.loads((root / "stats.json").read_text())
    mean = torch.tensor(stats["mean"]).reshape(3, 1, 1)
    std = torch.tensor(stats["std"]).reshape(3, 1, 1)
    train, val, test = (CifarSplit(root, split, mean, std) for split in SPLITS)
    if not train.class_names == val.class_names == test.class_names:
        raise ValueError("Class order differs across splits")
    if max_train_samples is not None:
        if max_train_samples < 1:
            raise ValueError("max_train_samples must be positive")
        if max_train_samples < len(train):
            train.indices = random.Random(seed).sample(train.indices, max_train_samples)
    return DatasetSplits(train, val, test, train.class_names)
