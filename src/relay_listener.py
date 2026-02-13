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

from dotenv import load_dotenv
from websockets.asyncio.client import connect

from services.mwl.create_worklist_item import CreateWorklistItem
from services.storage import MWLStorage

load_dotenv()

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")
SAS_TOKEN_EXPIRY_SECONDS = 3600

ACTIONS = {
    "worklist.create_item": CreateWorklistItem,
}


class RelayListener:
    """
    Socket Listener for Azure Relay.

    Listens for incoming messages from Azure Relay and processes worklist actions.
    Environment variables:
    AZURE_RELAY_NAMESPACE: Azure Relay namespace (default: relay-test.servicebus.windows.net)
    AZURE_RELAY_HYBRID_CONNECTION: Azure Relay hybrid connection name (default: relay-test-hc)
    AZURE_RELAY_KEY_NAME: Azure Relay shared access key name (default: RootManageSharedAccessKey)
    AZURE_RELAY_SHARED_ACCESS_KEY: Azure Relay shared access key (default: none)
    MWL_DB_PATH: Path to the MWL SQLite database file (default: /var/lib/pacs/worklist.db)
    """

    def __init__(self, storage: MWLStorage):
        self.storage = storage
        self.relay_uri = RelayURI()

    async def listen(self):
        """Listen for messages from Azure Relay."""

        logger.info(f"Connecting to Azure Relay: {self.relay_uri.hybrid_connection_name}...")

        async with connect(self.relay_uri.connection_url(), compression=None) as websocket:
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

        action_class = ACTIONS.get(action_name)
        if not action_class:
            raise ValueError(f"Unknown action: {action_name}")

        return action_class(self.storage).call(payload)


class RelayURI:
    def __init__(self):
        self.relay_namespace = os.getenv("AZURE_RELAY_NAMESPACE", "relay-test.servicebus.windows.net")
        self.hybrid_connection_name = os.getenv("AZURE_RELAY_HYBRID_CONNECTION", "relay-test-hc")
        self.key_name = os.getenv("AZURE_RELAY_KEY_NAME", "RootManageSharedAccessKey")
        self.shared_access_key = os.getenv("AZURE_RELAY_SHARED_ACCESS_KEY", "")

    def create_sas_token(self, expiry_seconds: int = SAS_TOKEN_EXPIRY_SECONDS) -> str:
        """Create SAS token for Azure Relay authentication."""
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

    def connection_url(self) -> str:
        token = self.create_sas_token()
        return (
            f"wss://{self.relay_namespace}/$hc/{self.hybrid_connection_name}"
            f"?sb-hc-action=listen&sb-hc-token={urllib.parse.quote_plus(token)}"
        )


async def main():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )

    logger.info("Socket Listener Starting...")
    storage = MWLStorage(db_path=DB_PATH)

    while True:
        try:
            await RelayListener(storage).listen()
        except KeyboardInterrupt:
            logger.warning("\nShutting down...")
            break
        except Exception as e:
            logger.warning(f"Connection error: {e}")
            logger.warning("Retrying in 5 seconds...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
