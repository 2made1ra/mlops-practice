"""Convert the raw CIFAR-10 archive (pickle) into PNG images and JSON annotations."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import pickle
import tarfile
from typing import TypedDict

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from tqdm import tqdm

from mlops_practice.ingest import CIFAR10_MD5, md5sum

TRAIN_BATCHES = [f"data_batch_{n}" for n in range(1, 6)]
TEST_BATCH = "test_batch"


class ImageRecord(TypedDict):
    image_id: str
    file_name: str
    label: int
    label_name: str
    sha256: str


class Annotations(TypedDict):
    classes: list[str]
    images: list[ImageRecord]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--archive",
        type=Path,
        default="data/raw/cifar-10-python.tar.gz",
        help="raw CIFAR-10 archive",
    )
    parser.add_argument("--md5", default=CIFAR10_MD5, help="expected MD5 of the archive")
    parser.add_argument(
        "--interim",
        type=Path,
        default="data/interim",
        help="directory for the unpacked archive and the full train annotations",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default="data/processed/cifar10",
        help="dataset root for images/ and annotations/",
    )

    args = parser.parse_args()

    return args


def extract(archive: Path, dest: Path) -> Path:
    """Unpack the archive into dest and return the cifar-10-batches-py directory."""
    result = dest / "cifar-10-batches-py"

    if result.is_dir():
        return result

    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")

    return result


def unpickle(path: Path) -> dict[bytes, object]:
    # Safe only because main() verifies the archive MD5 before anything is unpickled.
    with path.open("rb") as f:
        data: dict[bytes, object] = pickle.load(f, encoding="bytes")
    return data


def load_batch(path: Path) -> tuple[NDArray[np.uint8], list[int]]:
    """Read one pickled batch; return images of shape (N, 32, 32, 3) and labels."""
    batch = unpickle(path)
    # Rows are 3072 values: 1024 red, then 1024 green, then 1024 blue (CHW) -> HWC.
    images = np.asarray(batch[b"data"], dtype=np.uint8).reshape(-1, 3, 32, 32)
    labels = batch[b"labels"]
    assert isinstance(labels, list)
    return images.transpose(0, 2, 3, 1), [int(label) for label in labels]


def load_classes(batches_dir: Path) -> list[str]:
    """Read class names from batches.meta."""
    names = unpickle(batches_dir / "batches.meta")[b"label_names"]
    assert isinstance(names, list)
    return [name.decode() for name in names]


def save_png(image: NDArray[np.uint8], path: Path) -> str:
    """Write the image as PNG and return the sha256 of the written bytes."""
    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, format="PNG")
    data = buffer.getvalue()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def convert_split(
    images: NDArray[np.uint8], labels: list[int], prefix: str, classes: list[str], out: Path
) -> list[ImageRecord]:
    """Save every image as out/images/<prefix>_<NNNNN>.png and return their records."""
    (out / "images").mkdir(parents=True, exist_ok=True)
    records: list[ImageRecord] = []

    pairs = zip(images, labels, strict=True)
    for i, (image, label) in enumerate(tqdm(pairs, total=len(labels), desc=prefix)):
        image_id = f"{prefix}_{i:05d}"
        file_name = f"images/{image_id}.png"
        records.append(
            ImageRecord(
                image_id=image_id,
                file_name=file_name,
                label=label,
                label_name=classes[label],
                sha256=save_png(image, out / file_name),
            )
        )

    return records


def write_annotations(annotations: Annotations, path: Path) -> None:
    """Write annotations as JSON (create parent dirs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(annotations, indent=2) + "\n")


def main() -> None:
    args = parse_args()

    # pickle can run arbitrary code: only unpack an archive we can trust.
    if (actual := md5sum(args.archive)) != args.md5:
        raise SystemExit(f"MD5 mismatch for {args.archive}: expected {args.md5}, got {actual}")

    batches = extract(args.archive, args.interim)
    classes = load_classes(batches)

    parts = [load_batch(batches / name) for name in TRAIN_BATCHES]
    train_images = np.concatenate([images for images, _ in parts])
    train_labels = [label for _, labels in parts for label in labels]
    test_images, test_labels = load_batch(batches / TEST_BATCH)

    train = convert_split(train_images, train_labels, "train", classes, args.out)
    test = convert_split(test_images, test_labels, "test", classes, args.out)

    # The full train goes to interim/: the split step reads it and writes train/val to out/.
    train_path = args.interim / "cifar10" / "train.json"
    test_path = args.out / "annotations" / "test.json"
    write_annotations(Annotations(classes=classes, images=train), train_path)
    write_annotations(Annotations(classes=classes, images=test), test_path)

    print(f"Converted {len(train)} train and {len(test)} test images into {args.out}")
    print(f"Annotations: {train_path}, {test_path}")


if __name__ == "__main__":
    main()
