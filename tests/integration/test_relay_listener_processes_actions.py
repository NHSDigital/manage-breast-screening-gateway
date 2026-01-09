import json

import pytest

from relay_listener import RelayListener
from services.storage import MWLStorage


class TestRelayListenerProcessesActions:
    @pytest.fixture
    def payload(self):
        return {
            "action_id": "action-12345",
            "action_type": "worklist.create_item",
            "parameters": {
                "worklist_item": {
                    "participant": {
                        "nhs_number": "999123456",
                        "name": "SMITH^JANE",
                        "birth_date": "19900202",
                        "sex": "F",
                    },
                    "scheduled": {
                        "date": "20240615",
                        "time": "101500",
                    },
                    "procedure": {
                        "modality": "MG",
                        "study_description": "MAMMOGRAPHY",
                    },
                    "accession_number": "ACC999999",
                }
            },
        }

    @pytest.mark.asyncio
    async def test_relay_listener_creates_worklist_items(self, payload, tmp_dir, fake_relay):
        storage = MWLStorage(f"{tmp_dir}/test_worklist.db")
        listener = RelayListener(storage)
        relay_message = json.dumps({"accept": {"address": "wss://accept-url"}})

        with fake_relay(relay_message, json.dumps(payload)) as ws_client:
            await listener.listen()

        ws_client.send.assert_called_once_with(json.dumps({"status": "created", "action_id": "action-12345"}))
        stored_items = storage.find_worklist_items()
        assert len(stored_items) == 1
        item = stored_items[0]
        assert item.accession_number == "ACC999999"
        assert item.patient_id == "999123456"
