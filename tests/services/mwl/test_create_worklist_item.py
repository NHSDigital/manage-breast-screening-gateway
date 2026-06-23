from unittest.mock import patch

import pytest

from services.mwl.create_worklist_item import CreateWorklistItem
from services.storage import MWLStorage


class TestCreateWorklistItem:
    @pytest.fixture
    def db_file(tmp_path):
        return f"{tmp_path}/test.db"

    @pytest.fixture
    def mwl_storage(self, db_file):
        return MWLStorage(str(db_file))

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
