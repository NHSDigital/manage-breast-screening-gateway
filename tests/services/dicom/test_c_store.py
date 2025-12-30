from unittest.mock import PropertyMock, patch

import pytest
from pydicom import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian

from services.dicom.c_store import FAILURE, SUCCESS, CStore


class TestCStore:
    @pytest.fixture
    def mock_event(self):
        dataset = Dataset()
        dataset.AccessionNumber = "ABC123"
        dataset.SOPInstanceUID = "1.2.3.4.5.6"
        dataset.PatientID = "9990001112"
        file_meta = FileMetaDataset()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        event = PropertyMock()
        event.file_meta = file_meta
        event.dataset = dataset
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
        mock_storage.store_instance.assert_called_once_with(
            "1.2.3.4.5.6",
            subject.dataset_to_bytes(mock_event.dataset),
            {"accession_number": "ABC123", "patient_id": "9990001112"},
            "ae-title",
        )

    def test_storage_error_fails(self, mock_storage, mock_event):
        mock_storage.store_instance.side_effect = Exception("Nooooo!")
        subject = CStore(mock_storage)

        assert subject.call(mock_event) == FAILURE

    def test_failure_hexcode(self):
        assert FAILURE == 0xC000

    def test_success_hexcode(self):
        assert SUCCESS == 0x0000
