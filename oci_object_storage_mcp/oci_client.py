"""OCI Object Storage client using an OCI CLI security-token profile."""

from __future__ import annotations

import base64
import os
from typing import Any

import oci

from .ociclients import get_os_client


class ObjectStorageService:
    """Object Storage wrapper for the authenticated MCP caller."""

    def __init__(self, mcp_token: Any, region: str | None = None) -> None:
        region = region or os.getenv("OCI_REGION")
        if not region:
            raise RuntimeError("OCI_REGION must be set")
        self._client = get_os_client(mcp_token, region)
        self._namespace: str | None = None

    def _get_namespace(self) -> str:
        if self._namespace is None:
            self._namespace = self._client.get_namespace().data
        return self._namespace

    def list_buckets(self, compartment_id: str, limit: int = 100) -> dict[str, Any]:
        response = self._client.list_buckets(
            namespace_name=self._get_namespace(),
            compartment_id=compartment_id,
            limit=limit,
        )
        return {"buckets": [oci.util.to_dict(bucket) for bucket in response.data]}

    def list_objects(
        self,
        bucket_name: str,
        prefix: str | None = None,
        delimiter: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        response = self._client.list_objects(
            namespace_name=self._get_namespace(),
            bucket_name=bucket_name,
            prefix=prefix,
            delimiter=delimiter,
            start=start,
            end=end,
            limit=limit,
        )
        data = response.data
        return {
            "objects": [oci.util.to_dict(obj) for obj in (data.objects or [])],
            "prefixes": data.prefixes or [],
            "next_start_with": data.next_start_with,
        }

    def get_object(
        self, bucket_name: str, object_name: str, max_bytes: int = 1_048_576
    ) -> dict[str, Any]:
        if not 1 <= max_bytes <= 10 * 1_048_576:
            raise ValueError("max_bytes must be between 1 and 10 MiB")
        response = self._client.get_object(
            namespace_name=self._get_namespace(),
            bucket_name=bucket_name,
            object_name=object_name,
        )
        content = response.data.raw.read(max_bytes + 1)
        truncated = len(content) > max_bytes
        if truncated:
            content = content[:max_bytes]
        return {
            "object_name": object_name,
            "content_base64": base64.b64encode(content).decode("ascii"),
            "content_type": response.headers.get("content-type", "application/octet-stream"),
            "content_length": response.headers.get("content-length"),
            "etag": response.headers.get("etag"),
            "truncated": truncated,
        }
