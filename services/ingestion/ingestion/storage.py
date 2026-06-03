from __future__ import annotations

from datetime import datetime
from typing import Any

import boto3
import structlog
from botocore.config import Config

from ingestion.config import settings
from ingestion.schema import NormalizedDocument

log = structlog.get_logger(__name__)


def _client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_root_user,
        aws_secret_access_key=settings.minio_root_password,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        region_name="us-east-1",
    )


def _key(source: str, doc_id: str, kind: str, ext: str) -> str:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return f"source={source}/date={today}/{kind}/{doc_id}.{ext}"


def put_raw(source: str, doc_id: str, content: bytes, ext: str) -> str:
    key = _key(source, doc_id, kind="raw", ext=ext)
    _client().put_object(Bucket=settings.s3_bucket_bronze, Key=key, Body=content)
    log.info("bronze.put_raw", key=key, bytes=len(content))
    return key


def put_normalized(doc: NormalizedDocument) -> str:
    key = _key(doc.metadata.source, doc.metadata.doc_id, kind="text", ext="json")
    body = doc.model_dump_json(indent=2).encode("utf-8")
    _client().put_object(
        Bucket=settings.s3_bucket_bronze,
        Key=key,
        Body=body,
        ContentType="application/json",
    )
    log.info("bronze.put_normalized", key=key, bytes=len(body))
    return key


def object_exists(key: str) -> bool:
    try:
        _client().head_object(Bucket=settings.s3_bucket_bronze, Key=key)
        return True
    except Exception:
        return False


def doc_id_exists(source: str, doc_id: str) -> bool:
    """Check if this doc_id was ever written for this source, across any date partition.

    Lists objects with the `text/{doc_id}` suffix using prefix+contains semantics.
    For MinIO/S3 we list under `source=X/` and scan for the doc_id token; small partitions
    keep this O(N) reasonable for our scale.
    """
    prefix = f"source={source}/"
    paginator = _client().get_paginator("list_objects_v2")
    needle = f"/text/{doc_id}.json"
    try:
        for page in paginator.paginate(Bucket=settings.s3_bucket_bronze, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(needle):
                    return True
    except Exception as e:
        log.warning("bronze.list_failed", source=source, err=str(e))
    return False
