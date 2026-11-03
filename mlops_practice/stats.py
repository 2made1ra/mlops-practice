"""Compute per-channel normalization statistics (mean, std) over the train split only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TypedDict

import numpy as np
from PIL import Image
from tqdm import tqdm

from mlops_practice.split import load_annotations


class Stats(TypedDict):
    split: str
    num_images: int
    scale: str
    mean: list[float]
    std: list[float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default="data/processed/cifar10",
        help="dataset root with images/ and annotations/train.json; stats.json is written here",
    )
    return parser.parse_args()


def channel_stats(root: Path, file_names: list[str]) -> tuple[list[float], list[float]]:
    """Return per-channel (R, G, B) mean and std of pixel values scaled to [0, 1]."""
    # Running sums in float64: no need to hold all images as floats in memory.
    total = np.zeros(3)
    total_sq = np.zeros(3)
    pixels = 0
    for name in tqdm(file_names, desc="stats"):
        with Image.open(root / name) as img:
            x = np.asarray(img.convert("RGB"), dtype=np.float64).reshape(-1, 3) / 255.0
        total += x.sum(axis=0)
        total_sq += (x * x).sum(axis=0)
        pixels += x.shape[0]

    mean = total / pixels
    std = np.sqrt(total_sq / pixels - mean * mean)
    return [round(float(v), 6) for v in mean], [round(float(v), 6) for v in std]


def main() -> None:
    args = parse_args()

    train = load_annotations(args.out / "annotations" / "train.json")["images"]
    mean, std = channel_stats(args.out, [r["file_name"] for r in train])

    stats = Stats(split="train", num_images=len(train), scale="[0, 1]", mean=mean, std=std)
    path = args.out / "stats.json"
    path.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(f"mean={mean} std={std} over {len(train)} train images -> {path}")


if __name__ == "__main__":
    main()
