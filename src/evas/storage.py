"""S3 object storage helpers. Parses/builds s3:// URIs and wraps boto3."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any, cast

import boto3

from evas.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split an s3://bucket/key URI into (bucket, key)."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Not an s3:// URI: {uri}")
    rest = uri[len("s3://") :]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError(f"Malformed s3:// URI (need bucket and key): {uri}")
    return bucket, key


def build_s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


@lru_cache
def get_s3_client() -> S3Client:
    s = get_settings()
    return boto3.client(
        "s3",
        region_name=s.s3_region,
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
    )


def download_to_file(uri: str, dest_path: str) -> None:
    bucket, key = parse_s3_uri(uri)
    get_s3_client().download_file(bucket, key, dest_path)


def upload_file(local_path: str, bucket: str, key: str, content_type: str | None = None) -> str:
    extra = {"ContentType": content_type} if content_type else None
    get_s3_client().upload_file(local_path, bucket, key, ExtraArgs=extra)
    return build_s3_uri(bucket, key)


def list_objects(uri_prefix: str) -> list[str]:
    """List object URIs under an s3://bucket/prefix (paginated). Returns full s3:// URIs.

    The prefix need not name a key, so this does not use parse_s3_uri (which requires
    a key). Zero-byte "directory marker" keys (ending in /) are skipped.
    """
    if not uri_prefix.startswith("s3://"):
        raise ValueError(f"Not an s3:// URI: {uri_prefix}")
    rest = uri_prefix[len("s3://") :]
    bucket, _, prefix = rest.partition("/")
    if not bucket:
        raise ValueError(f"Malformed s3:// prefix (need a bucket): {uri_prefix}")
    client = get_s3_client()
    uris: list[str] = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            uris.append(build_s3_uri(bucket, key))
    return uris


def get_object_bytes(uri: str) -> bytes:
    bucket, key = parse_s3_uri(uri)
    resp = get_s3_client().get_object(Bucket=bucket, Key=key)
    data: bytes = resp["Body"].read()
    return data


def delete_object(uri: str) -> None:
    bucket, key = parse_s3_uri(uri)
    get_s3_client().delete_object(Bucket=bucket, Key=key)


def set_storage_class(uri: str, storage_class: str) -> None:
    """Transition an object to a different S3 storage class (e.g. GLACIER).

    Implemented as an in-place server-side copy. Not all S3-compatible backends
    (e.g. MinIO) honor every storage class; callers should record intent
    regardless of backend support.
    """
    bucket, key = parse_s3_uri(uri)
    get_s3_client().copy_object(
        Bucket=bucket,
        Key=key,
        CopySource={"Bucket": bucket, "Key": key},
        StorageClass=cast(Any, storage_class),
        MetadataDirective="COPY",
    )
