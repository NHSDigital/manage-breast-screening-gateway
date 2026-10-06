from unittest.mock import patch

import pytest
import requests

from services.dicom.validation_failure_notifier import ValidationFailureNotifier

MODULE = "services.dicom.validation_failure_notifier"


class TestNotify:
    @patch(f"{MODULE}.requests.patch")
    def test_reports_failure_to_the_cloud_api(self, mock_patch, local_dev_auth):
        mock_patch.return_value.status_code = 200

        notifier = ValidationFailureNotifier(api_endpoint="http://api.example")
        assert notifier.notify("action-123", "Missing PixelData") is True

        mock_patch.assert_called_once()
        args, kwargs = mock_patch.call_args
        assert args[0] == "http://api.example/action-123/failure"
        assert kwargs["json"] == {"error": "Missing PixelData"}
        assert kwargs["headers"] == {"Authorization": f"Bearer {local_dev_auth}"}

    @patch(f"{MODULE}.requests.patch")
    def test_uses_managed_identity_when_resource_configured(self, mock_patch, managed_identity_auth):
        """Regression test: deployed environments authenticate with the managed
        identity, exactly as uploads do - not the local-dev static token."""
        mock_patch.return_value.status_code = 200

        notifier = ValidationFailureNotifier(api_endpoint="http://api.example")
        assert notifier.notify("action-123", "boom") is True

        _, kwargs = mock_patch.call_args
        assert kwargs["headers"] == {"Authorization": f"Bearer {managed_identity_auth.token}"}
        managed_identity_auth.credential.get_token.assert_called_once_with(managed_identity_auth.resource)

    @pytest.mark.usefixtures("local_dev_auth")
    @patch(f"{MODULE}.requests.patch")
    def test_returns_false_on_non_200(self, mock_patch):
        mock_patch.return_value.status_code = 403
        mock_patch.return_value.text = "forbidden"

        notifier = ValidationFailureNotifier(api_endpoint="http://api.example")
        assert notifier.notify("action-123", "boom") is False

    @pytest.mark.usefixtures("local_dev_auth")
    @patch(f"{MODULE}.requests.patch")
    def test_returns_false_on_request_exception(self, mock_patch):
        mock_patch.side_effect = requests.exceptions.ConnectionError("no route")

        notifier = ValidationFailureNotifier(api_endpoint="http://api.example")
        assert notifier.notify("action-123", "boom") is False
