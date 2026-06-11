"""S3 object storage helpers. Parses/builds s3:// URIs and wraps boto3."""

from __future__ import annotations

import os
import re
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


def _cred_slug(credential_ref: str) -> str:
    """credential_ref -> env-safe slug, e.g. 'halo-readonly' -> 'HALO_READONLY'."""
    return re.sub(r"[^A-Z0-9]+", "_", credential_ref.upper()).strip("_")


def _client_kwargs(credential_ref: str | None) -> dict[str, Any]:
    """boto3 client kwargs for a source credential.

    An empty/None ref uses EVAS's default service credentials (env). A named ref
    resolves per-source secrets from env vars namespaced by the ref — never the
    DB, never code: EVAS_CRED_<SLUG>_ACCESS_KEY_ID / _SECRET_ACCESS_KEY and the
    optional _REGION / _ENDPOINT_URL. Missing keys raise a clear error, which the
    sync pipeline surfaces as a source error rather than a silent failure.
    """
    s = get_settings()
    if not credential_ref:
        return {
            "region_name": s.s3_region,
            "endpoint_url": s.s3_endpoint_url,
            "aws_access_key_id": s.aws_access_key_id,
            "aws_secret_access_key": s.aws_secret_access_key,
        }
    slug = _cred_slug(credential_ref)
    ak = os.environ.get(f"EVAS_CRED_{slug}_ACCESS_KEY_ID")
    sk = os.environ.get(f"EVAS_CRED_{slug}_SECRET_ACCESS_KEY")
    if not ak or not sk:
        raise ValueError(
            f"no credentials configured for credential_ref {credential_ref!r}; "
            f"set EVAS_CRED_{slug}_ACCESS_KEY_ID and EVAS_CRED_{slug}_SECRET_ACCESS_KEY"
        )
    return {
        "region_name": os.environ.get(f"EVAS_CRED_{slug}_REGION", s.s3_region),
        "endpoint_url": os.environ.get(f"EVAS_CRED_{slug}_ENDPOINT_URL", s.s3_endpoint_url),
        "aws_access_key_id": ak,
        "aws_secret_access_key": sk,
    }


@lru_cache
def get_s3_client(credential_ref: str | None = None) -> S3Client:
    """S3 client for a source credential (None = EVAS default). Cached per ref."""
    return boto3.client("s3", **_client_kwargs(credential_ref))


def configured_credential_refs() -> list[str]:
    """Credential refs that have keys configured in env (EVAS_CRED_<SLUG>_ACCESS_KEY_ID).

    Returns the slugs (the canonical, slug-stable ref names) so the UI can offer
    only credentials that will actually resolve. Empty in local/default setups.
    """
    pat = re.compile(r"^EVAS_CRED_(.+)_ACCESS_KEY_ID$")
    return sorted({m.group(1) for k in os.environ if (m := pat.match(k))})


def download_to_file(uri: str, dest_path: str, credential_ref: str | None = None) -> None:
    bucket, key = parse_s3_uri(uri)
    get_s3_client(credential_ref).download_file(bucket, key, dest_path)


def upload_file(local_path: str, bucket: str, key: str, content_type: str | None = None) -> str:
    extra = {"ContentType": content_type} if content_type else None
    get_s3_client().upload_file(local_path, bucket, key, ExtraArgs=extra)
    return build_s3_uri(bucket, key)


def list_objects(uri_prefix: str, credential_ref: str | None = None) -> list[str]:
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
    client = get_s3_client(credential_ref)
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


def presign_get(uri: str, expires_in: int = 3600, credential_ref: str | None = None) -> str:
    """Presigned GET URL for an object, so a browser can fetch it directly.

    Supports range requests (video seeking) natively. Against MinIO the URL
    points at the configured endpoint (reachable by the browser in dev);
    against real S3 it is a public-internet URL. For objects in a source bucket,
    pass the source's credential_ref so the URL is signed with the right keys.
    """
    bucket, key = parse_s3_uri(uri)
    return get_s3_client(credential_ref).generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


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
