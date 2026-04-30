"""
RelayListener
Receives worklist actions from manage-screening.
Supports creation of Modality Worklist Items.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from dotenv import load_dotenv
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedError

from environment import Environment
from services.mwl.create_worklist_item import CreateWorklistItem
from services.storage import MWLStorage
from telemetry import configure_telemetry

load_dotenv()

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")
AZURE_RELAY_SCOPE = "https://relay.azure.com/.default"
SAS_TOKEN_EXPIRY_SECONDS = 3600


class CredentialNotAvailableError(RuntimeError):
    pass


class RelayListener:
    """
    Socket Listener for Azure Relay.

    Listens for incoming messages from Azure Relay and processes worklist actions.
    Environment variables:
    AZURE_RELAY_NAMESPACE: Azure Relay namespace (default: relay-test.servicebus.windows.net)
    AZURE_RELAY_HYBRID_CONNECTION: Azure Relay hybrid connection name (default: relay-test-hc)
    MWL_DB_PATH: Path to the MWL SQLite database file (default: /var/lib/pacs/worklist.db)

    Non-production only (SAS token fallback):
    AZURE_RELAY_KEY_NAME: Shared access policy name (default: RootManageSharedAccessKey)
    AZURE_RELAY_SHARED_ACCESS_KEY: Shared access key value
    """

    def __init__(self, storage: MWLStorage):
        self.storage = storage
        self.relay_uri = RelayURI()

    async def listen(self):
        """Listen for messages from Azure Relay."""

        logger.info(f"Connecting to Azure Relay: {self.relay_uri.hybrid_connection_name}...")

        async with self._connect() as websocket:
            logger.info("Connected - waiting for worklist actions...")

            async for message in websocket:
                try:
                    data = json.loads(message)

                    if "accept" in data:
                        accept_url = data["accept"]["address"]
                        logger.info("Incoming connection...")

                        async with connect(accept_url, compression=None) as client_ws:
                            client_message = await asyncio.wait_for(client_ws.recv(), timeout=30)
                            payload = json.loads(client_message)
                            response = self.process_action(payload)

                            # Send acknowledgment
                            await client_ws.send(json.dumps(response))

                except asyncio.TimeoutError:
                    logger.error("Timeout waiting for message")
                except Exception as e:
                    logger.error(f"Error: {e}")

    def process_action(self, payload: dict):
        """Process incoming action payload."""
        action_name = payload.get("action_type", "no-op")

        if action_name == "echo":
            return {"status": "echo", "payload": payload}
        elif action_name == "worklist.create_item":
            return CreateWorklistItem(self.storage).call(payload)
        else:
            raise ValueError(f"Unsupported action: {action_name}")

    def _connect(self):
        """Connect to Azure Relay."""
        return connect(
            self.relay_uri.connection_url(),
            compression=None,
            additional_headers=self.relay_uri.auth_headers(),
        )


class RelayURI:
    def __init__(self):
        self.relay_namespace = os.getenv("AZURE_RELAY_NAMESPACE", "relay-test.servicebus.windows.net")
        self.hybrid_connection_name = os.getenv("AZURE_RELAY_HYBRID_CONNECTION", "relay-test-hc")
        self.key_name = os.getenv("AZURE_RELAY_KEY_NAME", "RootManageSharedAccessKey")
        self.shared_access_key = os.getenv("AZURE_RELAY_SHARED_ACCESS_KEY", "")
        self._env = Environment()
        self._credential = None if self._use_sas() else self._build_credential()

    def _use_sas(self) -> bool:
        return not self._env.production and bool(self.shared_access_key)

    def _build_credential(self):
        if self._env.production:
            return ManagedIdentityCredential()
        return DefaultAzureCredential()

    def connection_url(self) -> str:
        base = f"wss://{self.relay_namespace}/$hc/{self.hybrid_connection_name}?sb-hc-action=listen"
        if self._use_sas():
            token = self._create_sas_token()
            return f"{base}&sb-hc-token={urllib.parse.quote_plus(token)}"
        return base

    def auth_headers(self) -> dict:
        if self._use_sas():
            return {}
        if self._credential is None:
            raise CredentialNotAvailableError(
                "No credential available — _credential should never be None when not using SAS"
            )
        token = self._credential.get_token(AZURE_RELAY_SCOPE).token
        return {"Authorization": f"Bearer {token}"}

    def _create_sas_token(self, expiry_seconds: int = SAS_TOKEN_EXPIRY_SECONDS) -> str:
        uri = f"http://{self.relay_namespace}/{self.hybrid_connection_name}"
        encoded_uri = urllib.parse.quote_plus(uri)
        expiry = str(int(time.time() + expiry_seconds))
        signature = base64.b64encode(
            hmac.new(self.shared_access_key.encode(), f"{encoded_uri}\n{expiry}".encode(), hashlib.sha256).digest()
        )
        return (
            f"SharedAccessSignature sr={encoded_uri}"
            f"&sig={urllib.parse.quote_plus(signature)}"
            f"&se={expiry}&skn={self.key_name}"
        )


def verify_credentials():
    """
    Verify relay credentials are available at startup.

    In production, raises ClientAuthenticationError if managed identity is not configured.
    In non-production with a SAS key present, logs the auth method and returns immediately.
    """
    uri = RelayURI()
    if uri._use_sas():
        logger.info("Using SAS token authentication for Azure Relay.")
    else:
        if uri._credential is None:
            raise CredentialNotAvailableError(
                "No credential available — _credential should never be None when not using SAS"
            )
        uri._credential.get_token(AZURE_RELAY_SCOPE)
        credential_type = "ManagedIdentityCredential" if uri._env.production else "DefaultAzureCredential"
        logger.info(f"Azure Relay credentials verified ({credential_type}).")


async def main():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )
    configure_telemetry(service_name="relay-listener")

    logger.info("Socket Listener Starting...")
    verify_credentials()
    storage = MWLStorage(db_path=DB_PATH)

    while True:
        try:
            await RelayListener(storage).listen()
        except KeyboardInterrupt:
            logger.warning("\nShutting down...")
            break
        except ConnectionClosedError as e:
            code = e.rcvd.code if e.rcvd else "N/A"
            reason = e.rcvd.reason if e.rcvd else "N/A"
            logger.warning(f"Connection closed with code {code}: {reason}")
            logger.warning("Retrying in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.warning(f"Connection error: {e}")
            logger.warning("Retrying in 5 seconds...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
