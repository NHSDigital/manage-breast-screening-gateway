import json
from unittest.mock import AsyncMock, patch

import pytest

from relay_listener import RelayListener, RelayURI
from services.storage import WorklistItem

pytest_plugin = "pytest_asyncio"


class TestRelayListener:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setenv("WORKLIST_DB_PATH", "/tmp/test_worklist.db")
        monkeypatch.setenv("AZURE_RELAY_NAMESPACE", "test-namespace")
        monkeypatch.setenv("AZURE_RELAY_HYBRID_CONNECTION", "test-connection")
        monkeypatch.setenv("AZURE_RELAY_KEY_NAME", "test-key-name")
        monkeypatch.setenv("AZURE_RELAY_SHARED_ACCESS_KEY", "test-key-value")
        yield

    @pytest.fixture
    @patch("relay_listener.MWLStorage")
    def storage_instance(self, mock_mwl_storage):
        return mock_mwl_storage.return_value

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

    def test_relay_listener_initialization(self, storage_instance):
        subject = RelayListener(storage_instance)

        assert subject.storage == storage_instance
        assert isinstance(subject.relay_uri, RelayURI)
        assert subject.relay_uri.relay_namespace == "test-namespace"
        assert subject.relay_uri.hybrid_connection_name == "test-connection"
        assert subject.relay_uri.key_name == "test-key-name"
        assert subject.relay_uri.shared_access_key == "test-key-value"

    @pytest.mark.asyncio
    async def test_relay_listener_listen(self, storage_instance, payload):
        storage_instance.store_worklist_action.return_value = {"action_id": "action-12345", "status": "created"}
        subject = RelayListener(storage_instance)
        url = subject.relay_uri.connection_url()
        assert url.startswith("wss://test-namespace/$hc/test-connection")
        assert "sb-hc-token=" in url

        relay_message = json.dumps({"accept": {"address": "wss://accept-url"}})

        client_payload = json.dumps(payload)

        relay_ws = FakeWebSocket([relay_message])
        client_ws = FakeWebSocket([])
        client_ws.recv.return_value = client_payload

        relay_cm = AsyncMock()
        relay_cm.__aenter__.return_value = relay_ws
        relay_cm.__aexit__.return_value = None

        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client_ws
        client_cm.__aexit__.return_value = None

        with patch("relay_listener.connect", side_effect=[relay_cm, client_cm]):
            await subject.listen()

        client_ws.send.assert_called_once_with(json.dumps({"status": "created", "action_id": "action-12345"}))
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

    def test_process_action(self, storage_instance, payload):
        subject = RelayListener(storage_instance)

        response = subject.process_action(payload)
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

    def test_process_action_invalid_type(self, storage_instance, payload):
        subject = RelayListener(storage_instance)

        payload["action_type"] = "worklist.unknown_action"

        with pytest.raises(ValueError):
            response = subject.process_action(payload)
            assert response == {
                "status": "error",
                "action_id": "action-12345",
                "error": "Unknown action type: worklist.unknown_action",
            }

            storage_instance.store_worklist_item.assert_not_called()

    def test_relay_uri_create_sas_token(self):
        subject = RelayURI()
        token = subject.create_sas_token(expiry_seconds=3600)

        with patch("time.time", return_value=1000000):
            token = subject.create_sas_token(expiry_seconds=3600)

        assert token == (
            "SharedAccessSignature sr=http%3A%2F%2Ftest-namespace%2Ftest-connection"
            "&sig=PMcelSnwGlYX2xFo9Y2aGCg%2BvJ6LsHujiRrA1L6VnP0%3D&se=1003600&skn=test-key-name"
        )

    def test_relay_uri_connection_url(self):
        subject = RelayURI()
        with patch("time.time", return_value=1000000):
            url = subject.connection_url()

        assert url == (
            "wss://test-namespace/$hc/test-connection?sb-hc-action=listen"
            "&sb-hc-token=SharedAccessSignature+sr%3Dhttp%253A%252F%252Ftest-namespace"
            "%252Ftest-connection%26sig%3DPMcelSnwGlYX2xFo9Y2aGCg%252BvJ6LsHujiRrA1L6VnP0%253D%26se%3D1003600%26skn%3Dtest-key-name"
        )


class FakeWebSocket:
    """Async iterator + websocket mock."""

    def __init__(self, messages):
        self._messages = messages
        self.send = AsyncMock()
        self.recv = AsyncMock()

    def __aiter__(self):
        self._iter = iter(self._messages)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration
