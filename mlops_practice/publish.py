"""Upload the processed dataset to S3 under an immutable versioned prefix with a manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import TypedDict

from dotenv import load_dotenv

from mlops_practice.s3 import make_client, prefix_exists, upload_files
from mlops_practice.split import load_annotations

SPLITS = ("train", "val", "test")


class FileEntry(TypedDict):
    path: str
    size: int
    sha256: str


class Manifest(TypedDict):
    dataset: str
    version: str
    git_commit: str
    git_dirty: bool
    params: dict[str, int]
    num_images: dict[str, int]
    files: list[FileEntry]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default="data/processed/cifar10",
        help="local dataset root to upload",
    )
    parser.add_argument(
        "--params",
        type=Path,
        default="data/interim/cifar10/split_params.json",
        help="split parameters recorded by the split step",
    )
    parser.add_argument("--bucket", default=os.environ.get("S3_BUCKET"), help="target bucket")
    parser.add_argument("--prefix", default="processed/cifar10", help="key prefix for versions")
    parser.add_argument("--version", required=True, help="dataset version, e.g. v1")
    parser.add_argument("--workers", type=int, default=32, help="parallel uploads")
    parser.add_argument(
        "--check", action="store_true", help="only fail if the version exists, upload nothing"
    )
    args = parser.parse_args()
    if not args.bucket:
        parser.error("--bucket is required (or set S3_BUCKET in .env)")
    return args


def git(*cmd: str) -> str:
    return subprocess.run(["git", *cmd], capture_output=True, text=True, check=True).stdout


def file_entry(root: Path, relative: str) -> FileEntry:
    data = (root / relative).read_bytes()
    return FileEntry(path=relative, size=len(data), sha256=hashlib.sha256(data).hexdigest())


def build_manifest(root: Path, version: str, params: dict[str, int]) -> Manifest:
    """Describe the dataset at root: split sizes, metadata files, parameters, git commit."""
    metadata = [f"annotations/{split}.json" for split in SPLITS] + ["stats.json"]
    return Manifest(
        dataset="cifar10",
        version=version,
        git_commit=git("rev-parse", "HEAD").strip(),
        git_dirty=bool(git("status", "--porcelain", "--untracked-files=no").strip()),
        params=params,
        num_images={
            split: len(load_annotations(root / f"annotations/{split}.json")["images"])
            for split in SPLITS
        },
        files=[file_entry(root, name) for name in metadata],
    )


def main() -> None:
    load_dotenv()
    args = parse_args()
    client = make_client()
    prefix = f"{args.prefix}/{args.version}/"
    target = f"s3://{args.bucket}/{prefix}"

    # Versions are immutable: refuse instead of silently overwriting (even a partial upload).
    if prefix_exists(client, args.bucket, prefix):
        raise SystemExit(f"{target} already exists; pass a new version, e.g. --version v2")
    if args.check:
        print(f"{target} is free")
        return

    params: dict[str, int] = json.loads(args.params.read_text(encoding="utf-8"))
    manifest = build_manifest(args.out, args.version, params)

    images = sorted((args.out / "images").glob("*.png"))
    if len(images) != sum(manifest["num_images"].values()):
        raise SystemExit(f"{len(images)} PNG files in {args.out}/images do not match annotations")

    files = {f"{prefix}images/{p.name}": p for p in images}
    files |= {f"{prefix}{entry['path']}": args.out / entry["path"] for entry in manifest["files"]}
    upload_files(client, args.bucket, files, workers=args.workers)

    # The manifest goes last: a version without manifest.json is an interrupted upload.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        upload_files(client, args.bucket, {f"{prefix}manifest.json": path}, desc="manifest")

    print(f"Published {len(files) + 1} objects to {target}")


if __name__ == "__main__":
    main()
