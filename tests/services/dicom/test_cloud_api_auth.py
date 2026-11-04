from services.dicom.cloud_api_auth import auth_headers


class TestAuthHeaders:
    def test_managed_identity_token_when_resource_configured(self, managed_identity_auth):
        assert auth_headers() == {"Authorization": f"Bearer {managed_identity_auth.token}"}
        managed_identity_auth.credential.get_token.assert_called_once_with(managed_identity_auth.resource)

    def test_cloud_api_token_when_no_resource_configured(self, local_dev_auth):
        assert auth_headers() == {"Authorization": f"Bearer {local_dev_auth}"}

    def test_managed_identity_in_production_even_without_resource(self, monkeypatch, mock_managed_identity_credential):
        monkeypatch.delenv("CLOUD_API_RESOURCE", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "prod")

        assert auth_headers() == {"Authorization": "Bearer mi_token"}
        mock_managed_identity_credential.get_token.assert_called_once_with("")

    def test_empty_token_when_nothing_configured(self, monkeypatch):
        monkeypatch.delenv("CLOUD_API_RESOURCE", raising=False)
        monkeypatch.delenv("CLOUD_API_TOKEN", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)

        assert auth_headers() == {"Authorization": "Bearer "}
