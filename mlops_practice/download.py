"""Download the raw CIFAR-10 archive from S3 into data/raw/."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from mlops_practice.ingest import CIFAR10_MD5, md5sum, progress_bar
from mlops_practice.s3 import make_client, object_exists

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--bucket", default=os.environ.get("S3_BUCKET"), help="set bucket name")
    parser.add_argument("--key", default="raw/cifar-10-python.tar.gz", help="target object key")
    parser.add_argument(
        "--dest", type=Path, default=Path("data/raw"), help="set up destination path"
    )
    parser.add_argument("--md5", default=CIFAR10_MD5, help="MD5 checking type")
    args = parser.parse_args()

    if not args.bucket:
        parser.error("--bucket is required (or set S3_BUCKET in .env)")

    return args


def is_ready(path: Path, md5: str) -> bool:
    """Return True if the archive is already on disk and its MD5 matches."""
    return path.is_file() and md5sum(path) == md5


def download(client: S3Client, bucket: str, key: str, dest: Path) -> None:
    """Download s3://bucket/key to dest, writing via a temp file and renaming at the end."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(f"{dest.name}.part")

    meta = client.head_object(Bucket=bucket, Key=key)
    size = meta["ContentLength"]

    with progress_bar(size, "download") as bar:
        client.download_file(bucket, key, str(temp), Callback=bar.update)

    temp.replace(dest)


def main() -> None:
    load_dotenv()
    args = parse_args()
    archive = args.dest / Path(args.key).name

    if is_ready(archive, args.md5):
        print(f"{archive} already exists")
        return

    client = make_client()

    if not object_exists(client, args.bucket, args.key):
        raise SystemExit(f"s3://{args.bucket}/{args.key} not found, upload it first with ingest")

    download(client, args.bucket, args.key, archive)

    expected = args.md5
    if (actual := md5sum(archive)) != expected:
        archive.unlink()
        raise SystemExit(f"MD5 mismatch: expected {expected}, got {actual}")

    print(f"Downloaded s3://{args.bucket}/{args.key} -> {archive}")


if __name__ == "__main__":
    main()
