from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from services.dicom.upload_processor import UploadProcessor


@pytest.fixture
def mock_pacs_storage():
    """Create mock PACS storage."""
    storage = Mock()
    storage.storage_root = Path("/tmp/storage")
    return storage


@pytest.fixture
def mock_mwl_storage():
    """Create mock MWL storage."""
    return Mock()


@pytest.fixture
def mock_uploader():
    """Create mock DICOM uploader."""
    return Mock()


@pytest.fixture
def processor(mock_pacs_storage, mock_mwl_storage, mock_uploader):
    """Create UploadProcessor with mocked dependencies."""
    return UploadProcessor(
        pacs_storage=mock_pacs_storage,
        mwl_storage=mock_mwl_storage,
        uploader=mock_uploader,
        max_retries=3,
    )


class TestUploadProcessor:
    def test_process_batch_with_no_pending(self, processor, mock_pacs_storage):
        mock_pacs_storage.get_pending_uploads.return_value = []

        result = processor.process_batch(limit=10)

        assert result == 0
        mock_pacs_storage.get_pending_uploads.assert_called_once_with(limit=10, max_retries=3)

    def test_process_batch_processes_all_instances(self, processor, mock_pacs_storage, mock_uploader):
        mock_pacs_storage.get_pending_uploads.return_value = [
            {
                "sop_instance_uid": "1.2.3.1",  # gitleaks:allow
                "storage_path": "a/b/c.dcm",
                "accession_number": "ACC1",
                "upload_attempt_count": 0,
            },
            {
                "sop_instance_uid": "1.2.3.2",  # gitleaks:allow
                "storage_path": "d/e/f.dcm",
                "accession_number": "ACC2",
                "upload_attempt_count": 0,
            },
        ]
        mock_uploader.upload_dicom.return_value = True

        with patch.object(Path, "exists", return_value=True), patch.object(Path, "read_bytes", return_value=b"dicom"):
            result = processor.process_batch(limit=10)

        assert result == 2
        assert mock_uploader.upload_dicom.call_count == 2

    def test_upload_instance_success(self, processor, mock_pacs_storage, mock_mwl_storage, mock_uploader):
        instance = {
            "sop_instance_uid": "1.2.3.4",  # gitleaks:allow
            "storage_path": "ab/cd/file.dcm",
            "accession_number": "ACC123",
            "upload_attempt_count": 0,
        }
        mock_mwl_storage.get_source_message_id.return_value = "ACTION123"
        mock_uploader.upload_dicom.return_value = True

        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_bytes", return_value=b"dicom data"),
        ):
            result = processor.upload_instance(instance)

        assert result is True
        mock_pacs_storage.mark_upload_started.assert_called_once_with("1.2.3.4")  # gitleaks:allow
        mock_pacs_storage.mark_upload_complete.assert_called_once_with("1.2.3.4")  # gitleaks:allow
        mock_uploader.upload_dicom.assert_called_once_with("1.2.3.4", b"dicom data", "ACTION123")  # gitleaks:allow

    def test_upload_instance_file_not_found(self, processor, mock_pacs_storage):
        instance = {
            "sop_instance_uid": "1.2.3.4",  # gitleaks:allow
            "storage_path": "missing/file.dcm",
            "accession_number": "ACC123",
            "upload_attempt_count": 0,
        }

        with patch.object(Path, "exists", return_value=False):
            result = processor.upload_instance(instance)

        assert result is False
        mock_pacs_storage.mark_upload_started.assert_called_once()
        mock_pacs_storage.mark_upload_failed.assert_called_once()
        args = mock_pacs_storage.mark_upload_failed.call_args
        assert args[0][0] == "1.2.3.4"  # gitleaks:allow
        assert "not found" in args[0][1]

    def test_upload_instance_upload_failure(self, processor, mock_pacs_storage, mock_mwl_storage, mock_uploader):
        instance = {
            "sop_instance_uid": "1.2.3.4",  # gitleaks:allow
            "storage_path": "ab/cd/file.dcm",
            "accession_number": "ACC123",
            "upload_attempt_count": 1,
        }
        mock_mwl_storage.get_source_message_id.return_value = None
        mock_uploader.upload_dicom.return_value = False

        with patch.object(Path, "exists", return_value=True), patch.object(Path, "read_bytes", return_value=b"dicom"):
            result = processor.upload_instance(instance)

        assert result is False
        mock_pacs_storage.mark_upload_failed.assert_called_once()
        # attempt_count was 1, now 2, not permanent yet (max_retries=3)
        assert mock_pacs_storage.mark_upload_failed.call_args[1]["permanent"] is False

    def test_upload_instance_handles_exception(self, processor, mock_pacs_storage):
        instance = {
            "sop_instance_uid": "1.2.3.4",  # gitleaks:allow
            "storage_path": "ab/cd/file.dcm",
            "accession_number": "ACC123",
            "upload_attempt_count": 0,
        }

        with patch.object(Path, "exists", side_effect=Exception("Disk error")):
            result = processor.upload_instance(instance)

        assert result is False
        mock_pacs_storage.mark_upload_failed.assert_called_once()
        args = mock_pacs_storage.mark_upload_failed.call_args
        assert "Unexpected error" in args[0][1]


class TestBackoff:
    def test_backoff_increases_on_failure(self, processor, mock_pacs_storage, mock_uploader):
        mock_pacs_storage.get_pending_uploads.return_value = [
            {
                "sop_instance_uid": "1.2.3.4",  # gitleaks:allow
                "storage_path": "a/b.dcm",
                "accession_number": None,
                "upload_attempt_count": 0,
            },
        ]
        mock_uploader.upload_dicom.return_value = False

        with patch.object(Path, "exists", return_value=True), patch.object(Path, "read_bytes", return_value=b"dicom"):
            processor.process_batch()

        assert processor.backoff_delay == 1.0

    def test_backoff_capped_at_max(self, mock_pacs_storage, mock_mwl_storage, mock_uploader):
        processor = UploadProcessor(
            pacs_storage=mock_pacs_storage,
            mwl_storage=mock_mwl_storage,
            uploader=mock_uploader,
            initial_backoff=10.0,
            max_backoff=30.0,
            backoff_multiplier=2.0,
        )
        mock_pacs_storage.get_pending_uploads.return_value = [
            {
                "sop_instance_uid": "1.2.3.4",  # gitleaks:allow
                "storage_path": "a/b.dcm",
                "accession_number": None,
                "upload_attempt_count": 0,
            },
        ]
        mock_uploader.upload_dicom.return_value = False

        with patch.object(Path, "exists", return_value=True), patch.object(Path, "read_bytes", return_value=b"dicom"):
            processor.process_batch()
            assert processor.backoff_delay == 10.0

            processor.process_batch()
            assert processor.backoff_delay == 20.0

            processor.process_batch()
            assert processor.backoff_delay == 30.0  # Capped at max

            processor.process_batch()
            assert processor.backoff_delay == 30.0  # Still capped
