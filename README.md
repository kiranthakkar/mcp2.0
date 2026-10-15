# OCI Object Storage MCP server

A remote [FastMCP](https://gofastmcp.com/) 4.0 server for MCP 2.0, exposing three read-only OCI Object Storage tools.

> FastMCP 4.0.0b1 is a prerelease and is pinned exactly for reproducible MCP 2.0 compatibility. Validate its release notes before production deployment.

It provides:

- `listBuckets(compartment_id, limit)`
- `listObjects(bucket_name, prefix, delimiter, start, end, limit)`
- `getObject(bucket_name, object_name, max_bytes)` — returns base64 content and is capped at 1 MiB by default.

## Authentication model

There are two independent credentials:

1. **MCP client → server:** OAuth 2.1 / OIDC through an OCI IAM Identity Domain. FastMCP's `OCIProvider` uses the domain OIDC discovery document, manages the MCP OAuth bridge, and validates OCI-issued tokens.
2. **Server → OCI:** OCI IAM **Token Exchange Authentication**. For each tool
   call, the server exchanges the authenticated caller's IDCS JWT through a
   server-held confidential application and builds `TokenExchangeSigner`.

OAuth identifies callers; OCI permissions are those of the principal produced
by IDCS token exchange. Apply least-privilege IAM policies to that principal.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Configure AgentSafe as described below, then start the direct-IDCS server with
`python -m oci_object_storage_mcp.server_cimd`. The MCP endpoint is
`https://mcp.example.com/mcp`; terminate TLS before the application.
`MCP_PUBLIC_URL` must be the externally reachable HTTPS origin, not a
container-local address.

## OAuth token-exchange logging

The OAuth proxy makes its authorization-code and refresh-token exchanges with
`httpx2`. Set this variable before starting the server to log all IDCS HTTP
request/response activity, including the domain's `/oauth2/v1/token` endpoint:

```bash
export OAUTH_HTTP_LOG_LEVEL=DEBUG
```

`DEBUG` also enables the underlying `httpcore2` trace, which records connection,
TLS, request-send, response-header, and response-body lifecycle events. Example
output:

```text
connect_tcp.started host='idcs-…identity.oraclecloud.com' port=443
start_tls.complete return_value=<…>
send_request_headers.complete
send_request_body.complete
receive_response_headers.complete return_value=(b'HTTP/1.1', 400, b'Bad Request', [...])
HTTP Request: POST https://<identity-domain>.identity.oraclecloud.com/oauth2/v1/token "HTTP/1.1 200 OK"
```

The trace intentionally does not log request/response bodies, client credentials,
authorization codes, tokens, or the `Authorization` header. Set
`OAUTH_HTTP_LOG_LEVEL=INFO` for method/URL/status only, or `OFF` to disable it.

To log exact request and response bodies for all outbound IDCS calls, explicitly
opt in before starting the server:

```bash
export OAUTH_LOG_TOKEN_PAYLOAD=true
```

This logs values such as authorization codes, refresh tokens, PKCE verifiers, and
issued access tokens. Keep the resulting logs restricted, and unset the variable
after diagnosis. The HTTP `Authorization` header is deliberately not logged; with
`client_secret_post`, the client secret is part of the form body and will appear.

The specialized `server_ociidentitydomainproxy` variant requests configured
scopes at the authorization endpoint but deliberately omits `scope` from its
subsequent `/oauth2/v1/token` authorization-code exchange. The standard
`server_oauthprovider` uses the stock FastMCP `OIDCProxy` with
`extra_token_params={"scope": "", "resource": "…/mcp"}`. In the pinned
FastMCP version, the empty form value replaces the generated `scope` and is
omitted by the underlying HTTP client, while scopes remain present at the
authorization endpoint. `forward_resource=True` only forwards a resource
indicator to `/authorize`; `OAUTH_TOKEN_RESOURCE` (default:
`MCP_PUBLIC_URL/mcp`) supplies the resource indicator for `/oauth2/v1/token`.

## OCI IAM Identity Domain setup

In **Identity & Security → Domains → _your domain_ → Integrated applications**, add and activate a **Confidential Application**. Configure it as a client with **Authorization Code** and **Refresh Token** grants, then add this redirect URI exactly:

```text
https://mcp.example.com/auth/callback
```

Record its client ID and secret in your secret manager, configure the access-token audience/scopes required by your domain, then set the matching environment variables above. `OCIProvider` obtains the authorization, token, issuer, and JWKS endpoints from `OCI_CONFIG_URL`. The `MCP_OAUTH_SIGNING_KEY` is separate from the OCI client secret; generate and manage it as a long, random secret.

The domain's OpenID discovery document is `https://<identity-domain>.identity.oraclecloud.com/.well-known/openid-configuration`; use it to confirm the JWKS endpoint for your tenancy.

## OCI IAM minimums

Grant the OCI principal reached through token exchange read access only in the intended compartment, for example:

```text
Allow group <group-name> to read buckets in compartment <compartment-name>
Allow group <group-name> to read objects in compartment <compartment-name>
```

Keep `IDCS_CLIENT_SECRET` outside the repository and rotate it through your
secret manager.

## CIMD MCP client

`oci_object_storage_mcp.oauth_client` authenticates as a CIMD client rather
than registering a client dynamically. Set `CIMD_CLIENT_METADATA_URL` to a
public HTTPS JSON document with a non-root path, then run:

```bash
CIMD_CLIENT_METADATA_URL=https://mcp-client.example.com/.well-known/mcp-client.json \
python -m oci_object_storage_mcp.oauth_client
```

The hosted document must use that exact URL as `client_id`. IDCS requires an
exact redirect URI, so configure a fixed callback port in `.env` and use the
same value in the document:

```bash
MCP_OAUTH_CALLBACK_PORT=8765
```

```json
{
  "client_id": "https://mcp-client.example.com/.well-known/mcp-client.json",
  "client_name": "OCI Object Storage MCP client",
  "redirect_uris": ["http://localhost:8765/callback"],
  "grant_types": ["authorization_code"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "none",
  "scope": "openid"
}
```

Use `MCP_OAUTH_SCOPES` only when the authorization request needs an explicit
scope override. Do not place the CIMD URL in `OCI_CLIENT_ID`: that setting is
strictly the server's upstream OCI IAM Identity Domain confidential-client ID.

Before opening a browser, the client fetches and validates the CIMD document.
This makes errors such as an unreachable URL, invalid JSON, blocked private IP,
or a mismatched `client_id` explicit. The metadata URL must also be reachable
from the MCP server's runtime; otherwise its `/authorize` endpoint returns 400
and FastMCP reports the generic `ClientNotFoundError` message.

To trace every MCP-client request to the configured MCP endpoint and IDCS,
including request and response headers, set this diagnostic flag in `.env`:

```bash
MCP_CLIENT_LOG_HTTP_HEADERS=true
```

It logs `Authorization` bearer tokens and other sensitive headers. Restrict the
logs and set it back to `false` immediately after diagnosis.

After authentication, `oauth_client.py` lists and invokes each Object Storage
tool in order. Set these values before running it:

```bash
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..<your-compartment-id>
OCI_BUCKET_NAME=<bucket-name>
OCI_OBJECT_NAME=<object-name>
```

The sample OAuth client removes `offline_access` from the final authorization
request and sends `prompt=login`. OCI IDCS can return 401 when a non-browser
client preflights an authorization URL, so this sample opens the URL directly
in the default browser and also prints it for manual use.

## Direct IDCS tokens with CIMD

Use `server_cimd` when the MCP client, rather than this service, must call
IDCS `/oauth2/v1/token`. It is a resource server: it publishes IDCS as its
authorization server and verifies the IDCS JWT signature, issuer, audience,
and scopes using IDCS discovery/JWKS. It does not use `OCI_CLIENT_ID` or
`OCI_CLIENT_SECRET`.

Both `server_cimd` and `oauth_client` load their settings through AgentSafe
before reading any configuration. Initialize AgentSafe in the repository root,
put the real values in the ignored `.env.agent`, and compile it to an encrypted
`.env`:

```bash
agentsafe init --profile DEFAULT \
  --crypto-endpoint https://<vault>-crypto.kms.<region>.oraclecloud.com \
  --key-id <key-ocid>
cp .env.example .env.agent
# Edit .env.agent with the real MCP, IDCS, OCI, CIMD, and tool values.
agentsafe env encrypt

python -m oci_object_storage_mcp.server_cimd
```

Do not source the encrypted `.env` or use `dotenv`: AgentSafe decrypts it in
memory using the OCI profile selected by `.agentsafe/config` (or
`AGENTSAFE_PROFILE`). `.env.agent` is deliberately gitignored. The encrypted
`.env` and non-secret `.agentsafe/config` may be committed.

The MCP client discovers IDCS from the server's protected-resource metadata,
uses `CIMD_CLIENT_METADATA_URL` as its client ID, and exchanges its own code at
IDCS. `OCI_REQUIRED_SCOPES` is the single scope configuration: it is both
advertised to the MCP client and required in the IDCS access-token `scope`
claim. `OCI_AUDIENCE` independently validates the access-token `aud` claim.
`IDCS_CLIENT_ID` and `IDCS_CLIENT_SECRET` belong to the separate confidential
application authorized for OCI token exchange; they are never sent to MCP
clients.
For OCI Identity Domains, the server advertises the concrete host from the
discovery document's `authorization_endpoint`, while retaining the discovery
document's `issuer` for JWT validation. This avoids sending clients to the
certificate-incompatible `identity.oraclecloud.com` apex host.
