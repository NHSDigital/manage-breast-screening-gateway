import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.core.exceptions import ClientAuthenticationError
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close, CloseCode

from models import WorklistItem
from relay_listener import RelayListener, RelayURI, main, verify_credentials


class TestRelayListener:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setenv("MWL_DB_PATH", "/tmp/test_worklist.db")
        monkeypatch.setenv("AZURE_RELAY_NAMESPACE", "test-namespace")
        monkeypatch.setenv("AZURE_RELAY_HYBRID_CONNECTION", "test-connection")
        yield

    @pytest.fixture
    @patch("relay_listener.MWLStorage")
    def storage_instance(self, mock_mwl_storage):
        return mock_mwl_storage.return_value

    def test_relay_listener_initialization(self, storage_instance):
        """Relay listener initialization."""
        subject = RelayListener(storage_instance)

        assert subject.storage == storage_instance
        assert isinstance(subject.relay_uri, RelayURI)
        assert subject.relay_uri.relay_namespace == "test-namespace"
        assert subject.relay_uri.hybrid_connection_name == "test-connection"

    @pytest.mark.asyncio
    async def test_relay_listener_listen_echo(self, storage_instance, fake_relay):
        """Relay listener listen echo."""
        subject = RelayListener(storage_instance)

        relay_message = json.dumps({"accept": {"address": "wss://accept-url"}})
        client_payload = json.dumps({"action_type": "echo", "message": "Hello, Relay!"})

        with fake_relay(relay_message, client_payload) as client_ws:
            await subject.listen()

        client_ws.send.assert_called_once_with(
            json.dumps({"status": "echo", "payload": {"action_type": "echo", "message": "Hello, Relay!"}})
        )

    @pytest.mark.asyncio
    async def test_relay_listener_listen(self, storage_instance, listener_payload, fake_relay):
        """Relay listener listen."""
        storage_instance.store_worklist_action.return_value = {"action_id": "action-12345", "status": "created"}
        subject = RelayListener(storage_instance)

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

    def test_process_create_item_action(self, storage_instance, listener_payload):
        """Process create item action."""
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

    def test_process_update_item_status_action(self, storage_instance, listener_payload):
        """Process update item status action."""
        subject = RelayListener(storage_instance)

        subject.process_action(listener_payload)

        update_payload = {
            "action_id": "action-12345",
            "action_type": "worklist.update_status",
            "parameters": {"worklist_item": {"accession_number": "ACC999999", "status": "IN PROGRESS"}},
        }

        response = subject.process_action(update_payload)
        assert response == {"accession_number": "ACC999999", "status": "updated"}

        storage_instance.update_status.assert_called_once_with("ACC999999", "IN PROGRESS")

    def test_process_create_test_item_action_triggers_modality_emulator(self, storage_instance, listener_payload):
        """Process create test item action and trigger modality emulator."""
        subject = RelayListener(storage_instance)
        payload = dict(listener_payload)
        payload["action_type"] = "worklist.create_test_item"

        with patch.object(subject, "process_with_modality_emulator") as mock_emulator:
            response = subject.process_action(payload)

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
            )
        )

    def test_process_action_missing_keys(self, storage_instance, listener_payload):
        """Process action missing keys."""
        subject = RelayListener(storage_instance)

        del listener_payload["parameters"]["worklist_item"]["accession_number"]

        response = subject.process_action(listener_payload)
        assert response["status"] == "error"
        assert "Missing key" in response["message"]

        storage_instance.store_worklist_item.assert_not_called()

    def test_process_action_invalid_type(self, storage_instance, listener_payload):
        """Process action invalid type."""
        subject = RelayListener(storage_instance)

        listener_payload["action_type"] = "worklist.unknown_action"

        response = subject.process_action(listener_payload)
        assert response == {
            "status": "error",
            "message": "Unsupported action: worklist.unknown_action",
        }

        storage_instance.store_worklist_item.assert_not_called()


class TestRelayURIWithDefaultAzureCredential:
    """Non-production, no SAS key — uses DefaultAzureCredential."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setenv("AZURE_RELAY_NAMESPACE", "test-namespace")
        monkeypatch.setenv("AZURE_RELAY_HYBRID_CONNECTION", "test-connection")
        monkeypatch.delenv("AZURE_RELAY_SHARED_ACCESS_KEY", raising=False)
        yield

    def test_connection_url(self, mock_azure_credential):
        """Relay URI with default azure credential: Connection url."""
        subject = RelayURI()
        url = subject.connection_url()
        assert url.startswith("wss://test-namespace/$hc/test-connection?sb-hc-action=listen")
        assert "sb-hc-token=Bearer+test-token" in url

    def test_uses_default_azure_credential(self, mock_azure_credential):
        """Uses default azure credential."""
        with patch("relay_listener.DefaultAzureCredential") as mock_dac:
            mock_dac.return_value = mock_azure_credential
            subject = RelayURI()
            assert subject._credential is mock_dac.return_value


class TestRelayURIWithSasToken:
    """Non-production with SAS key present — uses SAS token."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setenv("AZURE_RELAY_NAMESPACE", "test-namespace")
        monkeypatch.setenv("AZURE_RELAY_HYBRID_CONNECTION", "test-connection")
        monkeypatch.setenv("AZURE_RELAY_KEY_NAME", "test-key-name")
        monkeypatch.setenv("AZURE_RELAY_SHARED_ACCESS_KEY", "test-key-value")
        yield

    def test_connection_url_includes_sas_token(self):
        """Connection url includes SAS token."""
        subject = RelayURI()
        url = subject.connection_url()
        assert url.startswith("wss://test-namespace/$hc/test-connection?sb-hc-action=listen")
        assert "sb-hc-token=SharedAccessSignature" in url

    def test_no_credential_is_created(self):
        """No credential is created."""
        with patch("relay_listener.DefaultAzureCredential") as mock_dac:
            with patch("relay_listener.ManagedIdentityCredential") as mock_mic:
                RelayURI()
                mock_dac.assert_not_called()
                mock_mic.assert_not_called()


class TestRelayURIInProduction:
    """Production environment — always uses ManagedIdentityCredential, never SAS."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setenv("AZURE_RELAY_NAMESPACE", "test-namespace")
        monkeypatch.setenv("AZURE_RELAY_HYBRID_CONNECTION", "test-connection")
        monkeypatch.setenv("ENVIRONMENT", "prod")
        yield

    def test_uses_managed_identity_credential(self, mock_azure_credential):
        """Uses managed identity credential."""
        with patch("relay_listener.ManagedIdentityCredential") as mock_mic:
            mock_mic.return_value = mock_azure_credential
            subject = RelayURI()
            assert subject._credential is mock_mic.return_value

    def test_sas_key_is_ignored(self, mock_azure_credential, monkeypatch):
        """SAS key is ignored."""
        monkeypatch.setenv("AZURE_RELAY_SHARED_ACCESS_KEY", "some-key")
        subject = RelayURI()
        assert not subject._use_sas()
        assert "sb-hc-token=Bearer+test-token" in subject.connection_url()


class TestVerifyCredentials:
    def test_logs_sas_when_key_present(self, monkeypatch):
        """Logs SAS when key present."""
        monkeypatch.setenv("AZURE_RELAY_SHARED_ACCESS_KEY", "test-key")
        with patch("relay_listener.logger") as mock_logger:
            verify_credentials()
        mock_logger.info.assert_called_with("Using SAS token authentication for Azure Relay.")

    def test_verifies_default_azure_credential_when_no_key(self, mock_azure_credential, monkeypatch):
        """Verifies default azure credential when no key."""
        monkeypatch.delenv("AZURE_RELAY_SHARED_ACCESS_KEY", raising=False)
        verify_credentials()
        mock_azure_credential.get_token.assert_called_with("https://relay.azure.net/.default")

    def test_verifies_managed_identity_in_production(self, mock_azure_credential, monkeypatch):
        """Verifies managed identity in production."""
        monkeypatch.setenv("ENVIRONMENT", "prod")
        verify_credentials()
        mock_azure_credential.get_token.assert_called_with("https://relay.azure.net/.default")

    def test_raises_client_authentication_error_on_credential_failure(self, monkeypatch):
        """Raises client authentication error on credential failure."""
        monkeypatch.delenv("AZURE_RELAY_SHARED_ACCESS_KEY", raising=False)
        with patch("relay_listener.DefaultAzureCredential") as mock:
            mock.return_value.get_token.side_effect = ClientAuthenticationError("no credentials")
            with pytest.raises(ClientAuthenticationError):
                verify_credentials()


@patch("relay_listener.logger", new_callable=MagicMock)
@patch("relay_listener.MWLStorage", new_callable=MagicMock)
@patch("relay_listener.RelayListener")
@patch("asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_main_handles_connection_closed_and_keyboard_interrupt(
    mock_sleep, mock_relay_listener, mock_mwl_storage, mock_logger
):
    """Main handles connection closed and keyboard interrupt."""
    relay_listener_instance = mock_relay_listener.return_value
    relay_listener_instance.listen = AsyncMock()

    relay_listener_instance.listen.side_effect = [
        ConnectionClosedError(Close(CloseCode.INTERNAL_ERROR, "Something went wrong"), None),
        ConnectionClosedError(Close(CloseCode.BAD_GATEWAY, "Bad gateway"), None),
        KeyboardInterrupt(),
    ]

    await main()

    assert relay_listener_instance.listen.call_count == 3
    mock_logger.info.assert_any_call("Socket Listener Starting...")
    mock_logger.warning.assert_any_call("Connection closed with code 1011: Something went wrong")
    mock_logger.warning.assert_any_call("Retrying in 5 seconds...")
    mock_logger.warning.assert_any_call("Connection closed with code 1014: Bad gateway")
    mock_logger.warning.assert_any_call("\nShutting down...")
