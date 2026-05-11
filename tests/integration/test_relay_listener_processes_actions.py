import json

import pytest

from models import WorklistItem
from relay_listener import RelayListener
from services.storage import MWLStorage


class TestRelayListenerProcessesActions:
    @pytest.fixture
    def update_payload(self):
        return {
            "action_id": "action-12345",
            "action_type": "worklist.update_item_status",
            "parameters": {"worklist_item": {"accession_number": "ACC999999", "status": "in progress"}},
        }

    @pytest.mark.asyncio
    async def test_relay_listener_creates_worklist_items(self, listener_payload, tmp_dir, fake_relay):
        storage = MWLStorage(f"{tmp_dir}/test_worklist.db")
        listener = RelayListener(storage)
        relay_message = json.dumps({"accept": {"address": "wss://accept-url"}})

        with fake_relay(relay_message, json.dumps(listener_payload)) as ws_client:
            await listener.listen()

        ws_client.send.assert_called_once_with(json.dumps({"status": "created", "action_id": "action-12345"}))
        stored_items = storage.find_worklist_items()
        assert len(stored_items) == 1
        item = stored_items[0]
        assert item.accession_number == "ACC999999"
        assert item.patient_id == "999123456"

    @pytest.mark.asyncio
    async def test_relay_listener_updates_worklist_item_status(self, update_payload, tmp_dir, fake_relay):
        storage = MWLStorage(f"{tmp_dir}/test_worklist.db")
        listener = RelayListener(storage)
        relay_message = json.dumps({"accept": {"address": "wss://accept-url"}})

        storage.store_worklist_item(
            WorklistItem(**{
                "accession_number": "ACC999999",
                "patient_id": "999123456",
                "patient_name": "Test^Patient",
                "patient_birth_date": "19900101",
                "patient_sex": "F",
                "scheduled_date": "20240101",
                "scheduled_time": "090000",
                "modality": "MG",
                "study_description": "Mammogram",
                "source_message_id": "action-12345",
            })
        )

        with fake_relay(relay_message, json.dumps(update_payload)) as ws_client:
            await listener.listen()

        ws_client.send.assert_called_once_with(json.dumps({"accession_number": "ACC999999", "status": "IN PROGRESS"}))
        stored_items = storage.find_worklist_items()
        assert len(stored_items) == 1
        item = stored_items[0]
        assert item.accession_number == "ACC999999"
        assert item.patient_id == "999123456"
