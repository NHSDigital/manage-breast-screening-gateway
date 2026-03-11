"""
ServiceBusCommandListener
Receives worklist actions from manage-screening via Azure Service Bus.
"""

import asyncio
import json
import logging
import os

from services.mwl.create_worklist_item import CreateWorklistItem
from services.storage import MWLStorage

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")

COMMANDS_QUEUE = os.getenv("SERVICE_BUS_COMMANDS_QUEUE", "worklist-commands")

ACTIONS = {
    "worklist.create_item": CreateWorklistItem,
}


class ServiceBusCommandListener:
    """Listens for worklist commands from Azure Service Bus queue."""

    def __init__(self, storage: MWLStorage):
        self.storage = storage
        self.connection_string = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "")
        self.queue_name = COMMANDS_QUEUE

    async def listen(self):
        from azure.servicebus.aio import ServiceBusClient

        logger.info(f"Connecting to Service Bus queue: {self.queue_name}...")

        async with ServiceBusClient.from_connection_string(self.connection_string) as client:
            async with client.get_queue_receiver(self.queue_name) as receiver:
                logger.info("Connected - waiting for worklist commands...")

                async for message in receiver:
                    try:
                        payload = json.loads(str(message))
                        logger.info(f"Received message: {payload.get('action_type', 'unknown')}")

                        result = self.process_action(payload)
                        logger.info(f"Processed: {result}")

                        await receiver.complete_message(message)
                    except Exception as e:
                        logger.error(f"Failed to process message: {e}")
                        await receiver.abandon_message(message)

    def process_action(self, payload: dict):
        action_name = payload.get("action_type", "no-op")

        action_class = ACTIONS.get(action_name)
        if not action_class:
            raise ValueError(f"Unknown action: {action_name}")

        return action_class(self.storage).call(payload)


async def main():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )

    logger.info("Service Bus Command Listener Starting...")
    storage = MWLStorage(db_path=DB_PATH)

    while True:
        try:
            await ServiceBusCommandListener(storage).listen()
        except KeyboardInterrupt:
            logger.warning("\nShutting down...")
            break
        except Exception as e:
            logger.error(f"Connection error: {e}")
            logger.info("Retrying in 5 seconds...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
