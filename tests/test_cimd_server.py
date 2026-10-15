import importlib
import sys

from fastmcp.server.auth.oidc_proxy import OIDCConfiguration


def test_cimd_server_is_a_direct_idcs_resource_server(monkeypatch):
    configuration = OIDCConfiguration(
        strict=False,
        issuer="https://identity.example.com/",
        authorization_endpoint="https://idcs.example.com/oauth2/v1/authorize",
        token_endpoint="https://idcs.example.com/oauth2/v1/token",
        jwks_uri="https://idcs.example.com/admin/v1/SigningCert/jwk",
    )
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://mcp.example.com")
    monkeypatch.setenv("OCI_CONFIG_URL", "https://idcs.example.com/.well-known/openid-configuration")
    monkeypatch.setenv("OCI_AUDIENCE", "aud1")
    monkeypatch.setenv("OCI_REQUIRED_SCOPES", "openid")
    monkeypatch.setattr(
        OIDCConfiguration,
        "get_oidc_configuration",
        staticmethod(lambda *_args, **_kwargs: configuration),
    )

    sys.modules.pop("oci_object_storage_mcp.server_cimd", None)
    module = importlib.import_module("oci_object_storage_mcp.server_cimd")

    provider = module.create_oauth_provider()

    assert str(provider.authorization_servers[0]) == "https://idcs.example.com"
    assert provider.token_verifier.issuer == "https://identity.example.com/"
    assert provider.token_verifier.audience == "aud1"
    assert provider.required_scopes == ["openid"]
    assert provider.get_challenge_scopes() == ["openid"]
