import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from service_bus_listener import ServiceBusCommandListener
from services.storage import WorklistItem


class TestServiceBusCommandListener:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setenv("MWL_DB_PATH", "/tmp/test_worklist.db")
        monkeypatch.setenv(
            "AZURE_SERVICE_BUS_CONNECTION_STRING",
            "Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=test",
        )
        yield

    @pytest.fixture
    def storage_instance(self):
        return MagicMock()

    @pytest.fixture
    def listener_payload(self):
        return {
            "action_id": "action-12345",
            "action_type": "worklist.create_item",
            "parameters": {
                "worklist_item": {
                    "accession_number": "ACC999999",
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
                }
            },
        }

    def test_listener_initialization(self, storage_instance):
        subject = ServiceBusCommandListener(storage_instance)

        assert subject.storage == storage_instance
        assert (
            subject.connection_string
            == "Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=test"
        )
        # queue_name uses module-level COMMANDS_QUEUE which defaults to worklist-commands
        assert subject.queue_name == "worklist-commands"

    def test_process_action(self, storage_instance, listener_payload):
        subject = ServiceBusCommandListener(storage_instance)

        response = subject.process_action(listener_payload)
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
            )
        )

    def test_process_action_invalid_type(self, storage_instance, listener_payload):
        subject = ServiceBusCommandListener(storage_instance)

        listener_payload["action_type"] = "worklist.unknown_action"

        with pytest.raises(ValueError) as exc_info:
            subject.process_action(listener_payload)

        assert "Unknown action" in str(exc_info.value)
        storage_instance.store_worklist_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_listen_processes_messages(self, storage_instance, listener_payload):
        subject = ServiceBusCommandListener(storage_instance)

        mock_message = MagicMock()
        mock_message.__str__ = MagicMock(return_value=json.dumps(listener_payload))

        mock_receiver = AsyncMock()
        mock_receiver.__aenter__ = AsyncMock(return_value=mock_receiver)
        mock_receiver.__aexit__ = AsyncMock(return_value=False)

        async def message_generator():
            yield mock_message
            # Generator ends naturally after one message

        mock_receiver.__aiter__ = lambda self: message_generator()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get_queue_receiver = MagicMock(return_value=mock_receiver)

        # Patch where ServiceBusClient is imported from (inside listen method)
        with patch(
            "azure.servicebus.aio.ServiceBusClient",
        ) as mock_sbc:
            mock_sbc.from_connection_string.return_value = mock_client
            await subject.listen()

        # Verify message was processed and completed
        storage_instance.store_worklist_item.assert_called_once()
        mock_receiver.complete_message.assert_called_once_with(mock_message)

    @pytest.mark.asyncio
    async def test_listen_abandons_failed_messages(self, storage_instance, listener_payload):
        subject = ServiceBusCommandListener(storage_instance)

        mock_message = MagicMock()
        mock_message.__str__ = MagicMock(return_value=json.dumps(listener_payload))

        mock_receiver = AsyncMock()
        mock_receiver.__aenter__ = AsyncMock(return_value=mock_receiver)
        mock_receiver.__aexit__ = AsyncMock(return_value=False)

        async def message_generator():
            yield mock_message
            # Generator ends naturally after one message

        mock_receiver.__aiter__ = lambda self: message_generator()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get_queue_receiver = MagicMock(return_value=mock_receiver)

        # Patch where ServiceBusClient is imported from (inside listen method)
        with patch(
            "azure.servicebus.aio.ServiceBusClient",
        ) as mock_sbc:
            mock_sbc.from_connection_string.return_value = mock_client

            def process_and_fail(payload):
                raise Exception("Processing failed")

            subject.process_action = process_and_fail
            await subject.listen()

        mock_receiver.abandon_message.assert_called_once_with(mock_message)
        mock_receiver.complete_message.assert_not_called()
