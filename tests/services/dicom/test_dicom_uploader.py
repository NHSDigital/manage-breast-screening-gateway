import io
from unittest.mock import Mock, patch

import requests

from services.dicom.dicom_uploader import DICOMUploader


class TestDICOMUploader:
    @patch("services.dicom.dicom_uploader.requests.post")
    def test_upload_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 201
        mock_post.return_value = mock_response

        uploader = DICOMUploader(api_endpoint="http://test.com/api/upload")

        dicom_bytes = b"fake dicom data"
        result = uploader.upload_dicom(
            sop_instance_uid="1.2.3.4.5",  # gitleaks:allow
            dicom_bytes=dicom_bytes,
            action_id="ACTION123",
        )

        assert result is True
        mock_post.assert_called_once()

        # Verify multipart form upload with BytesIO stream
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["X-Source-Message-ID"] == "ACTION123"
        assert "files" in call_kwargs
        file_tuple = call_kwargs["files"]["file"]
        assert file_tuple[0] == "1.2.3.4.5.dcm"  # gitleaks:allow
        assert isinstance(file_tuple[1], io.BytesIO)  # stream
        assert file_tuple[1].getvalue() == dicom_bytes  # content

    @patch("services.dicom.dicom_uploader.requests.post")
    def test_upload_without_action_id(self, mock_post):
        """Upload without action_id sends empty header (server will reject)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Missing X-Source-Message-ID header"
        mock_post.return_value = mock_response

        uploader = DICOMUploader()
        result = uploader.upload_dicom(sop_instance_uid="1.2.3", dicom_bytes=b"data", action_id=None)

        assert result is False
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["X-Source-Message-ID"] == ""

    @patch("services.dicom.dicom_uploader.requests.post")
    def test_upload_failure_status_code(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_post.return_value = mock_response

        uploader = DICOMUploader()
        result = uploader.upload_dicom("1.2.3", b"data", None)

        assert result is False

    @patch("services.dicom.dicom_uploader.requests.post")
    def test_upload_timeout(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout()

        uploader = DICOMUploader(timeout=5)
        result = uploader.upload_dicom("1.2.3", b"data", None)

        assert result is False

    @patch("services.dicom.dicom_uploader.requests.post")
    def test_upload_network_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError()

        uploader = DICOMUploader()
        result = uploader.upload_dicom("1.2.3", b"data", None)

        assert result is False
