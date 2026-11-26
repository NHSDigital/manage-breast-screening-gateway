import asyncio
import threading
from unittest.mock import patch

import pytest

from modality_emulator import ModalityEmulator
from models import WorklistItem
from services.mwl.create_test_worklist_item import CreateTestWorklistItem
from services.storage import WorklistItemExistsError


class TestCreateTestWorklistItem:
    @pytest.fixture
    @patch("relay_listener.MWLStorage")
    def storage_instance(self, mock_mwl_storage):
        return mock_mwl_storage.return_value

    def test_call_triggers_modality_emulator(self, storage_instance, listener_payload):
        """Create test item action triggers modality emulator."""
        payload = dict(listener_payload)
        payload["action_type"] = "worklist.create_test_item"
        subject = CreateTestWorklistItem(storage_instance)

        with patch.object(ModalityEmulator, "process_worklist_items") as mock_emulator:
            response = subject.call(payload)

        assert response == {"action_id": "action-12345", "status": "created"}
        mock_emulator.assert_called_once_with(
            patient_name=payload["parameters"]["worklist_item"]["participant"]["name"]
        )

        storage_instance.store_worklist_item.assert_called_once_with(
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

    def test_call_without_emulation(self, storage_instance, listener_payload):
        """Process create test item action with emulate_modality:false payload parameter."""
        subject = CreateTestWorklistItem(storage_instance)
        payload = dict(listener_payload)
        payload["parameters"]["emulate_modality"] = False
        payload["action_type"] = "worklist.create_test_item"

        with patch.object(ModalityEmulator, "process_worklist_items") as mock_emulator:
            response = subject.call(payload)

        assert response == {"action_id": "action-12345", "status": "created"}

        storage_instance.store_worklist_item.assert_called_once_with(
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

        mock_emulator.assert_not_called()

    def test_call_without_patient_name_returns_error(self, storage_instance, listener_payload):
        """Process create test item action without a patient name returns an error."""
        subject = CreateTestWorklistItem(storage_instance)
        payload = dict(listener_payload)
        payload["action_type"] = "worklist.create_test_item"
        del payload["parameters"]["worklist_item"]["participant"]["name"]

        with patch.object(ModalityEmulator, "process_worklist_items"):
            response = subject.call(payload)

        assert response == {
            "status": "error",
            "message": "No patient name provided for ModalityEmulator test item processing",
        }

    def test_call_with_missing_accession_number(self, storage_instance, listener_payload):
        """Process create test item action without an accession number returns an error."""
        subject = CreateTestWorklistItem(storage_instance)
        payload = dict(listener_payload)
        payload["action_type"] = "worklist.create_test_item"
        del payload["parameters"]["worklist_item"]["accession_number"]

        with patch.object(ModalityEmulator, "process_worklist_items"):
            response = subject.call(payload)

        assert response == {
            "status": "error",
            "message": "Missing key: 'accession_number'",
        }

    def test_call_with_existing_worklist_item(self, storage_instance, listener_payload):
        """Process create test item action with an existing worklist item returns exists status."""
        subject = CreateTestWorklistItem(storage_instance)
        payload = dict(listener_payload)
        payload["action_type"] = "worklist.create_test_item"

        storage_instance.store_worklist_item.side_effect = WorklistItemExistsError("ACC999999")

        with patch.object(ModalityEmulator, "process_worklist_items") as mock_emulator:
            response = subject.call(payload)

        assert response == {"status": "exists", "action_id": "action-12345"}
        mock_emulator.assert_not_called()

    def test_call_deletes_test_item_after_emulation(self, storage_instance, listener_payload):
        """Process create test item action deletes the test item once emulation has finished."""
        subject = CreateTestWorklistItem(storage_instance)
        payload = dict(listener_payload)
        payload["action_type"] = "worklist.create_test_item"

        calls = []
        storage_instance.delete_worklist_item.side_effect = lambda accession_number: calls.append("delete")

        def fake_process(*args, **kwargs):
            calls.append("emulate")

        with patch.object(ModalityEmulator, "process_worklist_items", side_effect=fake_process) as mock_emulator:
            response = subject.call(payload)

        assert response == {"action_id": "action-12345", "status": "created"}
        mock_emulator.assert_called_once_with(
            patient_name=payload["parameters"]["worklist_item"]["participant"]["name"]
        )
        storage_instance.delete_worklist_item.assert_called_once_with(
            payload["parameters"]["worklist_item"]["accession_number"]
        )
        assert calls == ["emulate", "delete"]

    def test_call_does_not_delete_test_item_when_emulation_fails(self, storage_instance, listener_payload):
        """A failed emulation leaves the test item in place for investigation."""
        subject = CreateTestWorklistItem(storage_instance)
        payload = dict(listener_payload)
        payload["action_type"] = "worklist.create_test_item"

        with patch.object(ModalityEmulator, "process_worklist_items", side_effect=RuntimeError("boom")):
            response = subject.call(payload)

        assert response == {"action_id": "action-12345", "status": "created"}
        storage_instance.delete_worklist_item.assert_not_called()

    def test_call_in_running_event_loop_calls_emulator(self, storage_instance, listener_payload):
        """Item must still exist while the scheduled emulator processes sample DICOM files."""
        subject = CreateTestWorklistItem(storage_instance)
        payload = dict(listener_payload)
        payload["action_type"] = "worklist.create_test_item"

        processing_started = threading.Event()
        finish_processing = threading.Event()

        def fake_process(*args, **kwargs):
            processing_started.set()
            assert finish_processing.wait(timeout=5), "Emulator was never released"

        async def run():
            response = subject.call(payload)
            assert await asyncio.to_thread(processing_started.wait, 5)
            storage_instance.delete_worklist_item.assert_not_called()
            finish_processing.set()
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            await asyncio.gather(*pending)
            return response

        with patch.object(
            ModalityEmulator,
            "process_worklist_items",
            side_effect=fake_process,
        ) as mock_emulator:
            response = asyncio.run(run())

        assert response == {"action_id": "action-12345", "status": "created"}
        mock_emulator.assert_called_once_with(
            patient_name=payload["parameters"]["worklist_item"]["participant"]["name"]
        )
        storage_instance.delete_worklist_item.assert_called_once_with(
            payload["parameters"]["worklist_item"]["accession_number"]
        )
