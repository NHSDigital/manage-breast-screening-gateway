import pytest

from service_bus_listener import ServiceBusCommandListener
from services.storage import MWLStorage


class TestServiceBusListenerProcessesActions:
    @pytest.mark.asyncio
    async def test_listener_creates_worklist_items(self, listener_payload, tmp_dir):
        storage = MWLStorage(f"{tmp_dir}/test_worklist.db")
        listener = ServiceBusCommandListener(storage)

        result = listener.process_action(listener_payload)

        assert result == {"status": "created", "action_id": "action-12345"}

        stored_items = storage.find_worklist_items()
        assert len(stored_items) == 1
        item = stored_items[0]
        assert item.accession_number == "ACC999999"
        assert item.patient_id == "999123456"
        assert item.patient_name == "SMITH^JANE"
        assert item.scheduled_date == "20240615"
        assert item.modality == "MG"
