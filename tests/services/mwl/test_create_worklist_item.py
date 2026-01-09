from unittest.mock import patch

from services.mwl.create_worklist_item import CreateWorklistItem
from services.storage import WorklistItem


@patch(f"{CreateWorklistItem.__module__}.MWLStorage")
class TestCreateWorklistItem:
    def test_call_success(self, mock_mwl_storage, listener_payload):
        mock_storage_instance = mock_mwl_storage.return_value
        subject = CreateWorklistItem(mock_storage_instance)

        response = subject.call(listener_payload)
        assert response == {"action_id": "action-12345", "status": "created"}

        mock_storage_instance.store_worklist_item.assert_called_once_with(
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
            )
        )

    def test_call_missing_action_id(self, mock_mwl_storage, listener_payload):
        mock_storage_instance = mock_mwl_storage.return_value
        subject = CreateWorklistItem(mock_storage_instance)

        del listener_payload["action_id"]

        response = subject.call(listener_payload)
        assert response["status"] == "error"
        assert "Missing action_id" in response["error"]

        mock_storage_instance.store_worklist_item.assert_not_called()

    def test_call_storage_exception(self, mock_mwl_storage, listener_payload):
        mock_storage_instance = mock_mwl_storage.return_value
        mock_storage_instance.store_worklist_item.side_effect = Exception("DB error")
        subject = CreateWorklistItem(mock_storage_instance)

        response = subject.call(listener_payload)
        assert response["status"] == "error"
        assert "DB error" in response["error"]

        mock_storage_instance.store_worklist_item.assert_called_once()
