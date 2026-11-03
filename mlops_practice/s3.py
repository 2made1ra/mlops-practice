"""Thin helpers around boto3 for the project's S3-compatible storage."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import mimetypes
import os
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from tqdm import tqdm

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is not set (see .env.example)")
    return value


def make_client() -> S3Client:
    """Create an S3 client for the endpoint and credentials from the environment / .env."""
    load_dotenv()
    return boto3.client(
        "s3",
        endpoint_url=_require_env("S3_ENDPOINT_URL"),
        aws_access_key_id=_require_env("S3_ACCESS_KEY"),
        aws_secret_access_key=_require_env("S3_SECRET_KEY"),
        region_name="us-east-1",
        config=Config(
            # Local S3 has no per-bucket DNS names: use http://host/bucket/key.
            s3={"addressing_style": "path"},
            # Newer botocore adds checksums that not every S3-compatible store accepts.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def object_exists(client: S3Client, bucket: str, key: str) -> bool:
    """Return True if the object exists, False if it does not; re-raise other errors."""
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as err:
        if err.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise
    return True


def prefix_exists(client: S3Client, bucket: str, prefix: str) -> bool:
    """Return True if at least one object key starts with prefix."""
    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
    return response.get("KeyCount", 0) > 0


def upload_files(
    client: S3Client,
    bucket: str,
    files: dict[str, Path],
    workers: int = 32,
    desc: str = "upload",
) -> None:
    """Upload {key: local path} in parallel; a boto3 client is safe to share between threads."""

    def upload(key: str, path: Path) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": content_type})

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(upload, key, path) for key, path in files.items()]
        for future in tqdm(as_completed(futures), total=len(futures), desc=desc):
            future.result()  # re-raise the first upload error
