"""Download the CIFAR-10 archive and store it unchanged in S3 under raw/."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Never
from urllib.request import urlopen

from dotenv import load_dotenv
from tqdm import tqdm

from mlops_practice.s3 import make_client, object_exists

CIFAR10_URL = "https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz"
# Published on https://www.cs.toronto.edu/~kriz/cifar.html
CIFAR10_MD5 = "c58f30108f718f92721af3b95e74349a"
CHUNK_SIZE = 1 << 20  # 1 MiB


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=CIFAR10_URL, help="archive to download")
    parser.add_argument("--md5", default=CIFAR10_MD5, help="expected MD5 of the archive")
    parser.add_argument("--bucket", default=os.environ.get("S3_BUCKET"), help="target bucket")
    parser.add_argument("--key", default="raw/cifar-10-python.tar.gz", help="target object key")
    args = parser.parse_args()
    if not args.bucket:
        parser.error("--bucket is required (or set S3_BUCKET in .env)")
    return args


def progress_bar(total: int | None, desc: str) -> tqdm[Never]:
    return tqdm(total=total, unit="B", unit_scale=True, unit_divisor=1024, desc=desc)


def download(url: str, dest: Path) -> None:
    with urlopen(url) as response, dest.open("wb") as f:
        # Without Content-Length the bar still shows bytes and speed, just no percentage.
        total = int(response.headers.get("Content-Length", 0)) or None
        with progress_bar(total, "download") as bar:
            while chunk := response.read(CHUNK_SIZE):
                f.write(chunk)
                bar.update(len(chunk))


def md5sum(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "md5").hexdigest()


def main() -> None:
    load_dotenv()
    args = parse_args()
    client = make_client()
    target = f"s3://{args.bucket}/{args.key}"

    # Raw data is immutable: never download or upload again if the object is already there.
    if object_exists(client, args.bucket, args.key):
        print(f"{target} already exists, nothing to do")
        return

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / Path(args.key).name
        print(f"Downloading {args.url} ...")
        download(args.url, archive)

        # Verify before uploading: a corrupted archive must never land in immutable raw/.
        if (actual := md5sum(archive)) != args.md5:
            raise SystemExit(f"MD5 mismatch: expected {args.md5}, got {actual}")

        # upload_file sends large files in parallel parts and reports bytes via Callback.
        with progress_bar(archive.stat().st_size, "upload") as bar:
            client.upload_file(str(archive), args.bucket, args.key, Callback=bar.update)
    print(f"Uploaded {target}")


if __name__ == "__main__":
    main()
