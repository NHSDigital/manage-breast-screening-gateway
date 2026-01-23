from io import BytesIO
from unittest.mock import Mock, PropertyMock, patch

import pydicom
import pytest
from pydicom.uid import JPEG2000

from services.dicom import FAILURE, SUCCESS
from services.dicom.c_store import CStore
from services.dicom.image_compressor import ImageCompressor


class TestCStore:
    @pytest.fixture
    def mock_event(self, dataset_with_pixels):
        """Create a mock DICOM event using the shared dataset fixture."""
        # Customize the shared dataset for these tests
        dataset_with_pixels.AccessionNumber = "ABC123"
        dataset_with_pixels.SOPInstanceUID = "1.2.3.4.5.6"  # gitleaks:allow
        dataset_with_pixels.PatientID = "9990001112"
        dataset_with_pixels.PatientName = "JANE^SMITH"
        dataset_with_pixels.StudyInstanceUID = "1.2.3.4.5.6.7"  # gitleaks:allow
        dataset_with_pixels.SOPClassUID = "1.2.840.10008.5.1.4.1.1.1.2"  # gitleaks:allow

        # Wrap in PropertyMock to simulate DICOM event
        event = PropertyMock()
        event.file_meta = dataset_with_pixels.file_meta
        event.dataset = dataset_with_pixels
        event.assoc.requestor.ae_title = "ae-title"
        return event

    @pytest.fixture
    @patch(f"{CStore.__module__}.PACSStorage")
    def mock_storage(self, mock_pacs_storage):
        return mock_pacs_storage.return_value

    def test_no_sop_instance_uid_fails(self, mock_storage, mock_event):
        subject = CStore(mock_storage)
        mock_event.dataset.SOPInstanceUID = None

        assert subject.call(mock_event) == FAILURE

    def test_no_patient_id_fails(self, mock_storage, mock_event):
        subject = CStore(mock_storage)
        mock_event.dataset.PatientID = None

        assert subject.call(mock_event) == FAILURE

    def test_existing_sop_instance_uid(self, mock_storage, mock_event):
        mock_storage.instance_exists.return_value = True
        subject = CStore(mock_storage)

        assert subject.call(mock_event) == SUCCESS

    def test_valid_event_is_stored(self, mock_storage, mock_event):
        mock_storage.instance_exists.return_value = False
        subject = CStore(mock_storage)

        assert subject.call(mock_event) == SUCCESS

        # Verify store_instance was called with correct metadata
        # Note: bytes will be compressed, so we can't compare exact bytes
        call_args = mock_storage.store_instance.call_args
        assert call_args[0][0] == "1.2.3.4.5.6"  # gitleaks:allow
        assert call_args[0][2] == {  # Metadata
            "accession_number": "ABC123",
            "patient_id": "9990001112",
            "patient_name": "JANE^SMITH",
        }
        assert call_args[0][3] == "ae-title"  # AE Title

    def test_storage_error_fails(self, mock_storage, mock_event):
        mock_storage.store_instance.side_effect = Exception("Nooooo!")
        subject = CStore(mock_storage)

        assert subject.call(mock_event) == FAILURE

    def test_failure_hexcode(self):
        assert FAILURE == 0xC000

    def test_success_hexcode(self):
        assert SUCCESS == 0x0000

    def test_compressor_is_called(self, mock_storage, mock_event):
        mock_storage.instance_exists.return_value = False
        mock_compressor = Mock(spec=ImageCompressor)
        mock_compressor.compress.return_value = mock_event.dataset

        subject = CStore(mock_storage, compressor=mock_compressor)
        assert subject.call(mock_event) == SUCCESS

        mock_compressor.compress.assert_called_once()

    def test_compression_applied_on_storage(self, mock_storage, mock_event):
        """Verify images are compressed before storage (integration test with real compressor)."""
        mock_storage.instance_exists.return_value = False
        # Use real ImageCompressor to verify end-to-end compression
        subject = CStore(mock_storage, compressor=ImageCompressor())

        assert subject.call(mock_event) == SUCCESS

        # Verify stored bytes are JPEG 2000 compressed
        stored_bytes = mock_storage.store_instance.call_args[0][1]
        stored_ds = pydicom.dcmread(BytesIO(stored_bytes), force=True)
        assert stored_ds.file_meta.TransferSyntaxUID == JPEG2000
