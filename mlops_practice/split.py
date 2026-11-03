"""Split the full CIFAR-10 train into stratified train/val annotation files."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import random

from mlops_practice.convert import Annotations, ImageRecord, write_annotations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--train",
        type=Path,
        default="data/interim/cifar10/train.json",
        help="full train annotations written by convert",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default="data/processed/cifar10",
        help="dataset root; train/val go to <out>/annotations/",
    )
    parser.add_argument("--val-size", type=int, default=5000, help="images moved to val")
    parser.add_argument(
        "--seed", type=int, default=42, help="need to fix seed for correct repeating"
    )

    return parser.parse_args()


def load_annotations(path: Path) -> Annotations:
    """Read an annotation file written by convert."""
    annotation: Annotations = json.loads(path.read_text(encoding="utf-8"))
    return annotation


def stratified_split(
    records: list[ImageRecord], val_size: int, seed: int
) -> tuple[list[ImageRecord], list[ImageRecord]]:
    """Return (train, val): val takes the same share of every class, chosen by seed."""
    by_label: defaultdict[int, list[ImageRecord]] = defaultdict(list)
    for record in records:
        by_label[record["label"]].append(record)

    rng = random.Random(seed)
    val_ids: set[str] = set()
    # Fixed class order: the generator yields values in sequence, so order changes the result.
    for label in sorted(by_label):
        group = by_label[label]
        k = round(val_size * len(group) / len(records))
        val_ids.update(record["image_id"] for record in rng.sample(group, k))

    if len(val_ids) != val_size:
        raise ValueError(
            f"val-size {val_size} cannot be split evenly across classes "
            f"(stratified share gives {len(val_ids)})"
        )

    train = [r for r in records if r["image_id"] not in val_ids]
    val = [r for r in records if r["image_id"] in val_ids]
    return sorted(train, key=lambda r: r["image_id"]), sorted(val, key=lambda r: r["image_id"])


def main() -> None:
    args = parse_args()

    full = load_annotations(args.train)
    records = full["images"]
    if not 0 < args.val_size < len(records):
        raise SystemExit(f"val-size must be between 1 and {len(records) - 1}, got {args.val_size}")

    try:
        train, val = stratified_split(records, args.val_size, args.seed)
    except ValueError as err:
        raise SystemExit(str(err)) from err

    # Every original train image lands in exactly one of the two files.
    train_ids = {r["image_id"] for r in train}
    val_ids = {r["image_id"] for r in val}
    assert train_ids.isdisjoint(val_ids)
    assert train_ids | val_ids == {r["image_id"] for r in records}

    classes = full["classes"]
    annotations = args.out / "annotations"
    write_annotations(Annotations(classes=classes, images=train), annotations / "train.json")
    write_annotations(Annotations(classes=classes, images=val), annotations / "val.json")

    print(
        f"Split {len(records)} train images: {len(train)} train / {len(val)} val "
        f"(seed {args.seed})"
    )


if __name__ == "__main__":
    main()
