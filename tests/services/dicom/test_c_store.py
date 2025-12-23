from services.dicom.c_store import CStore, SUCCESS, FAILURE
from unittest.mock import patch, MagicMock
import pytest


class TestCStore:
    @pytest.fixture
    @patch(f"{CStore.__module__}.PACSStorage")
    def mock_storage(self, mock_pacs_storage):
        return mock_pacs_storage.return_value

    def test_no_sop_instance_uid(self):
        subject = CStore("storage")
        event = MagicMock()
        event.dataset.return_value = {"SOPInstanceUID": None}

        assert subject.call("9990001112", event) == FAILURE

    def test_existing_sop_instance_uid(self, mock_storage):
        mock_storage.instance_exists.return_value = True
        subject = CStore(mock_storage)
        event = MagicMock()
        event.dataset.return_value = {"SOPInstanceUID": "this-uuid-exists"}

        assert subject.call("9990001112", event) == SUCCESS

    def test_valid_event_is_stored(self, mock_storage):
        mock_storage.instance_exists.return_value = False
        subject = CStore(mock_storage)
        event = MagicMock()
        event.dataset.return_value = {"SOPInstanceUID": "an-unsaved-uuid"}

        assert subject.call("9990001112", event) == SUCCESS

    def test_storage_raises(self, mock_storage):
        mock_storage.store_instance.side_effect = Exception("Nooooo!")
        subject = CStore(mock_storage)
        event = MagicMock()
        event.dataset.return_value = {"SOPInstanceUID": "an-unsaved-uuid"}

        assert subject.call("9990001112", event) == FAILURE
