from unittest.mock import MagicMock, patch

import pytest

from models import WorklistItem
from services.mwl.create_worklist_item import CreateWorklistItem
from services.storage import MWLStorage


class TestCreateWorklistItem:
    @pytest.fixture
    def db_file(self, tmp_dir):
        return tmp_dir / "test.db"

    @pytest.fixture
    def mwl_storage(self, db_file):
        return MWLStorage(db_file)

    def test_call_success(self, mwl_storage, listener_payload):
        """Create worklist item: Call success."""
        subject = CreateWorklistItem(mwl_storage)

        response = subject.call(listener_payload)
        assert response == {"action_id": "action-12345", "status": "created"}

    def test_call_missing_action_id(self, mwl_storage, listener_payload):
        """Create worklist item: Call missing action id."""
        subject = CreateWorklistItem(mwl_storage)

        del listener_payload["action_id"]

        response = subject.call(listener_payload)
        assert response["status"] == "error"
        assert response["message"] == "Missing key: 'action_id'"

    def test_call_missing_accession_number(self, mwl_storage, listener_payload):
        """Create worklist item: Call missing accession number."""
        subject = CreateWorklistItem(mwl_storage)

        del listener_payload["parameters"]["worklist_item"]["accession_number"]

        response = subject.call(listener_payload)
        assert response["status"] == "error"
        assert response["message"] == "Missing key: 'accession_number'"

    def test_call_existing_worklist_item(self, mwl_storage, listener_payload):
        """Create worklist item: Call existing worklist item."""
        CreateWorklistItem(mwl_storage).call(listener_payload)

        subject = CreateWorklistItem(mwl_storage)

        response = subject.call(listener_payload)
        assert response == {"status": "exists", "action_id": "action-12345"}

    @patch(f"{CreateWorklistItem.__module__}.MWLStorage.store_worklist_item", side_effect=Exception("DB error"))
    def test_call_storage_exception(self, _, mwl_storage, listener_payload):
        """Create worklist item: Call storage exception."""
        subject = CreateWorklistItem(mwl_storage)

        response = subject.call(listener_payload)
        assert response["status"] == "error"
        assert "DB error" in response["message"]

    def test_call_with_patient_id(self, listener_payload):
        """Create worklist item: Call with patient_id."""
        mwl_storage = MagicMock(spec=MWLStorage)
        subject = CreateWorklistItem(mwl_storage)

        # Remove nhs_number and add patient_id
        participant = listener_payload["parameters"]["worklist_item"]["participant"]
        participant["patient_id"] = "PID-12345"

        response = subject.call(listener_payload)
        assert response == {"status": "created", "action_id": "action-12345"}
        mwl_storage.store_worklist_item.assert_called_once_with(
            WorklistItem(
                accession_number="ACC999999",
                patient_id="PID-12345",
                patient_name="SMITH^JANE",
                patient_birth_date="19900202",
                patient_sex="F",
                scheduled_date="20240615",
                scheduled_time="101500",
                modality="MG",
                study_description="MAMMOGRAPHY",
                source_message_id="action-12345",
                source_system_url="https://example.run-breast-screening.nhs.uk",
            )
        )

    def test_call_with_nhs_number_and_no_patient_id(self, listener_payload):
        """Create worklist item: Call with nhs_number and no patient_id."""
        mwl_storage = MagicMock(spec=MWLStorage)
        subject = CreateWorklistItem(mwl_storage)

        # Ensure nhs_number is present and patient_id is not
        participant = listener_payload["parameters"]["worklist_item"]["participant"]
        participant["nhs_number"] = "999123456"

        response = subject.call(listener_payload)
        assert response == {"status": "created", "action_id": "action-12345"}
        mwl_storage.store_worklist_item.assert_called_once_with(
            WorklistItem(
                accession_number="ACC999999",
                patient_id="999123456",
                patient_name="SMITH^JANE",
                patient_birth_date="19900202",
                patient_sex="F",
                scheduled_date="20240615",
                scheduled_time="101500",
                modality="MG",
                study_description="MAMMOGRAPHY",
                source_message_id="action-12345",
                source_system_url="https://example.run-breast-screening.nhs.uk",
            )
        )
