import base64
from types import SimpleNamespace

from oci_object_storage_mcp import oci_client, ociclients
from oci_object_storage_mcp.oci_client import ObjectStorageService


class Raw:
    def __init__(self, value: bytes):
        self.value = value

    def read(self, _size: int) -> bytes:
        return self.value


class OCIModel:
    swagger_types = {"name": "str"}

    def __init__(self, name: str):
        self.name = name


def test_object_storage_service_uses_token_exchange_client(monkeypatch):
    token = SimpleNamespace(token="idcs-access-token")
    client = SimpleNamespace()
    calls = []
    monkeypatch.setattr(
        oci_client,
        "get_os_client",
        lambda received_token, region: calls.append((received_token, region)) or client,
        raising=False,
    )

    service = ObjectStorageService(token, region="us-sanjose-1")

    assert service._client is client
    assert calls == [(token, "us-sanjose-1")]


def test_token_exchange_signer_uses_the_authenticated_token(monkeypatch):
    token = SimpleNamespace(token="idcs-access-token")
    captured = {}

    def signer(**kwargs):
        captured.update(kwargs)
        return "signer"

    monkeypatch.setenv("IDCS_DOMAIN", "https://idcs.example.com")
    monkeypatch.setenv("IDCS_CLIENT_ID", "exchange-client")
    monkeypatch.setenv("IDCS_CLIENT_SECRET", "exchange-secret")
    monkeypatch.setattr(ociclients, "TokenExchangeSigner", signer)

    assert ociclients.get_oci_signer(token) == "signer"
    assert captured == {
        "jwt_or_func": "idcs-access-token",
        "oci_domain_url": "https://idcs.example.com",
        "client_id": "exchange-client",
        "client_secret": "exchange-secret",
    }


def test_list_buckets_serializes_oci_sdk_models():
    service = ObjectStorageService.__new__(ObjectStorageService)
    service._namespace = "namespace"
    service._client = SimpleNamespace(
        list_buckets=lambda **_: SimpleNamespace(data=[OCIModel("bucket-a")])
    )

    result = service.list_buckets("ocid1.compartment.oc1..example")

    assert result == {"buckets": [{"name": "bucket-a"}]}


def test_list_objects_serializes_oci_sdk_models():
    service = ObjectStorageService.__new__(ObjectStorageService)
    service._namespace = "namespace"
    service._client = SimpleNamespace(
        list_objects=lambda **_: SimpleNamespace(
            data=SimpleNamespace(
                objects=[OCIModel("object-a")], prefixes=["folder/"], next_start_with=None
            )
        )
    )

    result = service.list_objects("example-bucket")

    assert result == {
        "objects": [{"name": "object-a"}],
        "prefixes": ["folder/"],
        "next_start_with": None,
    }


def test_get_object_encodes_and_caps_response():
    service = ObjectStorageService.__new__(ObjectStorageService)
    service._namespace = "namespace"
    service._client = SimpleNamespace(
        get_object=lambda **_: SimpleNamespace(
            data=SimpleNamespace(raw=Raw(b"abcdef")),
            headers={"content-type": "text/plain", "content-length": "6", "etag": "abc"},
        )
    )

    result = service.get_object("bucket", "file.txt", max_bytes=3)

    assert result["content_base64"] == base64.b64encode(b"abc").decode()
    assert result["truncated"] is True
    assert result["content_type"] == "text/plain"
