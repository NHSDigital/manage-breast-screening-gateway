"""PACS DICOM Server

Provides C-STORE SCP (Service Class Provider) for receiving DICOM images.
"""

import logging
import os

from pynetdicom import AE, StoragePresentationContexts, evt

from services.dicom.c_echo import CEcho
from services.dicom.c_store import CStore
from services.storage import PACSStorage

logger = logging.getLogger(__name__)


class PACSServer:
    """DICOM PACS Server with C-STORE support."""

    def __init__(
        self,
        ae_title: str = "SCREENING_PACS",
        port: int = 4244,
        storage_path: str = "/var/lib/pacs/storage",
        db_path: str = "/var/lib/pacs/pacs.db",
    ):
        """
        Initialize PACS server.

        Args:
            ae_title: Application Entity title
            port: Port to listen on
            storage_path: Directory for DICOM file storage
            db_path: Path to SQLite database
        """
        self.ae_title = ae_title
        self.port = port
        self.storage = PACSStorage(db_path, storage_path)
        self.ae = None

    def start(self):
        """Start the PACS server and listen for incoming connections."""
        logger.info(f"Starting PACS server: {self.ae_title} on port {self.port}")

        self.ae = AE(ae_title=self.ae_title)
        self.ae.supported_contexts = StoragePresentationContexts

        handlers = [(evt.EVT_C_ECHO, CEcho().call), (evt.EVT_C_STORE, CStore(self.storage).call)]

        logger.info(f"PACS server listening on 0.0.0.0:{self.port}")
        logger.info(f"Storage: {self.storage.storage_root}")
        logger.info(f"Database: {self.storage.db_path}")

        self.ae.start_server(("0.0.0.0", self.port), evt_handlers=handlers)  # type: ignore

    def stop(self):
        """Stop the PACS server."""
        if self.ae:
            logger.info("Stopping PACS server")
            self.ae.shutdown()
        self.storage.close()


def main():
    """Main entry point for PACS server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    ae_title = os.getenv("PACS_AET", "SCREENING_PACS")
    port = int(os.getenv("PACS_PORT", "4244"))
    storage_path = os.getenv("PACS_STORAGE_PATH", "/var/lib/pacs/storage")
    db_path = os.getenv("PACS_DB_PATH", "/var/lib/pacs/pacs.db")

    server = PACSServer(ae_title, port, storage_path, db_path)

    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        server.stop()


if __name__ == "__main__":
    main()
