from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture
def local_dev_auth(monkeypatch):
    """Local-dev auth config: static CLOUD_API_TOKEN, no managed identity.
    Yields the configured token for assertions.
    """
    monkeypatch.delenv("CLOUD_API_RESOURCE", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("CLOUD_API_TOKEN", "env_access_token")
    return "env_access_token"


@pytest.fixture
def mock_managed_identity_credential():
    """Mock the Azure credential (no env changes). Yields the mock, with
    get_token returning a token of "mi_token"."""
    with patch("services.dicom.cloud_api_auth.ManagedIdentityCredential") as credential_cls:
        credential = credential_cls.return_value
        credential.get_token.return_value.token = "mi_token"
        yield credential


@pytest.fixture
def managed_identity_auth(monkeypatch, mock_managed_identity_credential):
    """Deployed-environment auth config: CLOUD_API_RESOURCE set, credential
    mocked. Yields the mock credential plus the token/resource."""
    resource = "https://example.com/.default"
    monkeypatch.setenv("CLOUD_API_RESOURCE", resource)
    yield SimpleNamespace(credential=mock_managed_identity_credential, token="mi_token", resource=resource)
