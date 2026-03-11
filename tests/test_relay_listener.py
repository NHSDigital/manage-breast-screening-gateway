import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close, CloseCode

from relay_listener import RelayListener, RelayURI, main
from services.storage import WorklistItem


class TestRelayListener:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setenv("MWL_DB_PATH", "/tmp/test_worklist.db")
        monkeypatch.setenv("AZURE_RELAY_NAMESPACE", "test-namespace")
        monkeypatch.setenv("AZURE_RELAY_HYBRID_CONNECTION", "test-connection")
        monkeypatch.setenv("AZURE_RELAY_KEY_NAME", "test-key-name")
        monkeypatch.setenv("AZURE_RELAY_SHARED_ACCESS_KEY", "test-key-value")
        yield

    @pytest.fixture
    @patch("relay_listener.MWLStorage")
    def storage_instance(self, mock_mwl_storage):
        return mock_mwl_storage.return_value

    def test_relay_listener_initialization(self, storage_instance):
        subject = RelayListener(storage_instance)

        assert subject.storage == storage_instance
        assert isinstance(subject.relay_uri, RelayURI)
        assert subject.relay_uri.relay_namespace == "test-namespace"
        assert subject.relay_uri.hybrid_connection_name == "test-connection"
        assert subject.relay_uri.key_name == "test-key-name"
        assert subject.relay_uri.shared_access_key == "test-key-value"

    @pytest.mark.asyncio
    async def test_relay_listener_listen(self, storage_instance, listener_payload, fake_relay):
        storage_instance.store_worklist_action.return_value = {"action_id": "action-12345", "status": "created"}
        subject = RelayListener(storage_instance)
        url = subject.relay_uri.connection_url()
        assert url.startswith("wss://test-namespace/$hc/test-connection")
        assert "sb-hc-token=" in url

        relay_message = json.dumps({"accept": {"address": "wss://accept-url"}})

        client_payload = json.dumps(listener_payload)

        with fake_relay(relay_message, client_payload) as client_ws:
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

    def test_process_action(self, storage_instance, listener_payload):
        subject = RelayListener(storage_instance)

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
        subject = RelayListener(storage_instance)

        listener_payload["action_type"] = "worklist.unknown_action"

        with pytest.raises(ValueError):
            response = subject.process_action(listener_payload)
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


@patch("relay_listener.logger", new_callable=MagicMock)
@patch("relay_listener.MWLStorage", new_callable=MagicMock)
@patch("relay_listener.RelayListener")
@patch("asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_main_handles_connection_closed_and_keyboard_interrupt(
    mock_sleep, mock_relay_listener, mock_mwl_storage, mock_logger
):
    relay_listener_instance = mock_relay_listener.return_value
    relay_listener_instance.listen = AsyncMock()

    relay_listener_instance.listen.side_effect = [
        ConnectionClosedError(Close(CloseCode.INTERNAL_ERROR, "ExpiredToken"), None),
        ConnectionClosedError(Close(CloseCode.INTERNAL_ERROR, "Something else"), None),
        ConnectionClosedError(Close(CloseCode.BAD_GATEWAY, "Bad gateway"), None),
        KeyboardInterrupt(),
    ]

    await main()

    assert relay_listener_instance.listen.call_count == 4
    mock_logger.info.assert_any_call("Socket Listener Starting...")
    mock_logger.info.assert_any_call("SAS token expired, refreshing...")
    mock_logger.warning.assert_any_call("Connection closed with code 1011: Something else")
    mock_logger.warning.assert_any_call("Retrying in 5 seconds...")
    mock_logger.warning.assert_any_call("Connection closed with code 1014: Bad gateway")
    mock_logger.warning.assert_any_call("Retrying in 5 seconds...")
    mock_logger.warning.assert_any_call("\nShutting down...")
