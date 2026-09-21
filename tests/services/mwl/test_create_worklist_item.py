from unittest.mock import patch

import pytest

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

    def test_worklist_marked_in_progress_on_success(self, mwl_storage, listener_payload):
        """Worklist item is marked in progress after creation."""
        subject = CreateWorklistItem(mwl_storage)

        response = subject.call(listener_payload)
        assert response == {"action_id": "action-12345", "status": "created"}

        item = mwl_storage.get_worklist_item("ACC999999")
        assert item is not None
        assert item.status == "IN PROGRESS"

    def test_worklist_marked_in_progress_on_existing_item(self, mwl_storage, listener_payload):
        """Worklist item is marked in progress even if it already exists."""
        subject = CreateWorklistItem(mwl_storage)

        # First call to create the item
        response1 = subject.call(listener_payload)
        assert response1 == {"action_id": "action-12345", "status": "created"}

        # Second call to simulate existing item
        response2 = subject.call(listener_payload)
        assert response2 == {"status": "exists", "action_id": "action-12345"}

        # Check that the status is still IN PROGRESS
        item = mwl_storage.get_worklist_item("ACC999999")
        assert item is not None
        assert item.status == "IN PROGRESS"
