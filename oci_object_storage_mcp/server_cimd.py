"""Direct-IDCS OAuth resource server for the OCI Object Storage MCP tools.

Unlike ``server_oauthprovider``, this server does not proxy OAuth or hold an
IDCS client secret.  MCP clients obtain their own authorization code and token
from IDCS (including through CIMD), then present the IDCS access token here.
"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit

from fastmcp import FastMCP
from starlette.responses import PlainTextResponse
from starlette.requests import Request
from fastmcp.server.auth import JWTVerifier, RemoteAuthProvider
from fastmcp.server.auth.oidc_proxy import OIDCConfiguration
from fastmcp.server.dependencies import get_access_token

from .agentsafe_config import load_agentsafe_environment
from .oci_client import ObjectStorageService


# FastMCP constructs the auth provider at module import time, so decrypt the
# AgentSafe environment before building the provider below.
load_agentsafe_environment()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value


def _scopes(name: str, default: str = "") -> list[str]:
    return os.getenv(name, default).split()


def get_oidc_configuration() -> OIDCConfiguration:
    """Load the issuer and JWKS URI from the operator-configured IDCS discovery URL."""
    return OIDCConfiguration.get_oidc_configuration(
        _required("OCI_CONFIG_URL"), strict=False, timeout_seconds=30
    )


def authorization_server_url(configuration: OIDCConfiguration) -> str:
    """Return the concrete IDCS authorization-server origin.

    OCI discovery uses ``https://identity.oraclecloud.com/`` as the token
    issuer, but its authorization endpoint is hosted on a tenant-specific
    ``idcs-…identity.oraclecloud.com`` hostname.  The issuer is correct for
    JWT validation, whereas clients must use the latter host for OAuth metadata
    discovery and authorization; the wildcard TLS certificate does not cover
    the apex issuer hostname.
    """
    endpoint = urlsplit(str(configuration.authorization_endpoint))
    if not endpoint.scheme or not endpoint.netloc:
        raise RuntimeError("IDCS discovery document has an invalid authorization_endpoint")
    return f"{endpoint.scheme}://{endpoint.netloc}"


def create_oauth_provider() -> RemoteAuthProvider:
    """Advertise IDCS and validate its access tokens without token exchange."""
    configuration = get_oidc_configuration()
    validation_scopes = _scopes("OCI_REQUIRED_SCOPES", "openid")

    verifier = JWTVerifier(
        jwks_uri=str(configuration.jwks_uri),
        issuer=str(configuration.issuer),
        audience=_required("OCI_AUDIENCE"),
        required_scopes=validation_scopes,
    )
    return RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[authorization_server_url(configuration)],
        base_url=_required("MCP_PUBLIC_URL").rstrip("/"),
        resource_name="OCI Object Storage MCP",
    )


mcp = FastMCP("OCI Object Storage", auth=create_oauth_provider())


def _caller_access_token():
    """Read the authenticated caller's token before dispatching thread work."""
    access_token = get_access_token()
    if access_token is None:
        raise RuntimeError("Authenticated access token is required for OCI token exchange")
    return access_token


@mcp.tool(name="listBuckets")
async def list_buckets(compartment_id: str, limit: int = 100) -> dict:
    """List Object Storage buckets in an OCI compartment."""
    access_token = _caller_access_token()
    return await asyncio.to_thread(
        lambda: ObjectStorageService(access_token).list_buckets(compartment_id, limit)
    )


@mcp.tool(name="listObjects")
async def list_objects(
    bucket_name: str,
    prefix: str | None = None,
    delimiter: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 100,
) -> dict:
    """List Object Storage objects in a bucket."""
    access_token = _caller_access_token()
    return await asyncio.to_thread(
        lambda: ObjectStorageService(access_token).list_objects(
            bucket_name, prefix, delimiter, start, end, limit
        )
    )


@mcp.tool(name="getObject")
async def get_object(
    bucket_name: str, object_name: str, max_bytes: int = 1_048_576
) -> dict:
    """Read an object and return base64 content."""
    access_token = _caller_access_token()
    return await asyncio.to_thread(
        lambda: ObjectStorageService(access_token).get_object(
            bucket_name, object_name, max_bytes
        )
    )


def main() -> None:
    mcp.run(
        transport="http",
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8000")),
        path="/mcp",
    )

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    """This custom route can be used to run health check against MCP server.
    If you deploy load balancer, it can use /health URL to run the health check."""
    return PlainTextResponse("OK")

if __name__ == "__main__":
    main()
