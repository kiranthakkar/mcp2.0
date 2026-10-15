"""OCI SDK clients authenticated through OCI IAM token exchange."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

import oci
from oci.auth.signers import TokenExchangeSigner
from oci.object_storage import ObjectStorageClient


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be set for OCI token exchange")
    return value


def _domain_url() -> str:
    """Return the concrete Identity Domain origin used by token exchange."""
    configured = os.getenv("IDCS_DOMAIN")
    if configured:
        return configured.rstrip("/")

    discovery_url = _required("OCI_CONFIG_URL")
    parsed = urlsplit(discovery_url)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError("OCI_CONFIG_URL must be an HTTPS discovery URL")
    return f"{parsed.scheme}://{parsed.netloc}"


def get_oci_signer(mcp_token: Any) -> TokenExchangeSigner:
    """Exchange the authenticated MCP caller's IDCS JWT for an OCI signer."""
    token = getattr(mcp_token, "token", None)
    if not token:
        raise RuntimeError("An authenticated MCP access token is required")

    return TokenExchangeSigner(
        jwt_or_func=token,
        oci_domain_url=_domain_url(),
        client_id=_required("IDCS_CLIENT_ID"),
        client_secret=_required("IDCS_CLIENT_SECRET"),
    )


def get_os_client(mcp_token: Any, region: str) -> ObjectStorageClient:
    """Create an Object Storage client for the current authenticated caller."""
    return oci.object_storage.ObjectStorageClient(
        config={"region": region}, signer=get_oci_signer(mcp_token)
    )
