"""Thin helpers around boto3 for the project's S3-compatible storage."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

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
