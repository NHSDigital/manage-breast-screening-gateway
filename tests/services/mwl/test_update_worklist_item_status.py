import pytest

from models import WorklistItem
from services.mwl.update_worklist_item_status import UpdateWorklistItemStatus
from services.storage import MWLStorage


class TestUpdateWorklistItemStatus:
    @pytest.fixture
    def worklist_item_data(self):
        return {
            "accession_number": "ACC123",
            "modality": "MG",
            "patient_birth_date": "19800101",
            "patient_id": "1234567890",
            "patient_name": "Jane^Doe",
            "scheduled_date": "20240101",
            "scheduled_time": "120000",
            "source_message_id": "action-12345",
        }

    @pytest.fixture
    def status_update_payload(self):
        return {
            "action_id": "action-12345",
            "action_type": "worklist.update_item_status",
            "parameters": {"worklist_item": {"accession_number": "ACC123", "status": "completed"}},
        }

    @pytest.fixture
    def db_file(self, tmp_path) -> str:
        return f"{tmp_path}/test.db"

    @pytest.fixture
    def mwl_storage(self, db_file: str):
        return MWLStorage(db_file)

    def test_call_success(self, mwl_storage, worklist_item_data, status_update_payload):
        mwl_storage.store_worklist_item(WorklistItem(**worklist_item_data))
        mwl_storage.update_status("ACC123", "IN PROGRESS")

        subject = UpdateWorklistItemStatus(mwl_storage)
        response = subject.call(status_update_payload)
        assert response == {"accession_number": "ACC123", "status": "COMPLETED"}

    def test_call_missing_keys(self, mwl_storage, status_update_payload):
        subject = UpdateWorklistItemStatus(mwl_storage)

        del status_update_payload["parameters"]["worklist_item"]["status"]

        response = subject.call(status_update_payload)
        assert response["status"] == "error"
        assert "Missing key" in response["message"]

    def test_call_nonexistent_item(self, mwl_storage, status_update_payload):
        subject = UpdateWorklistItemStatus(mwl_storage)

        response = subject.call(status_update_payload)
        assert response["status"] == "error"
        assert response["message"] == "Worklist item 'ACC123' not found"

    def test_call_invalid_status_transition(self, mwl_storage, worklist_item_data, status_update_payload):
        subject = UpdateWorklistItemStatus(mwl_storage)

        mwl_storage.store_worklist_item(WorklistItem(**worklist_item_data))

        status_update_payload["parameters"]["worklist_item"]["status"] = "SCHEDULED"

        response = subject.call(status_update_payload)
        assert response["status"] == "error"
        assert response["message"] == "Cannot transition to 'SCHEDULED'"
