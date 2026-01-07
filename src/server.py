"""PACS and MWL DICOM Servers

Provides:
- C-STORE SCP (Service Class Provider) for receiving DICOM images (PACS)
- C-FIND SCP for modality worklist management (MWL)
"""

import logging
import os

from pynetdicom import AE, StoragePresentationContexts, evt
from pynetdicom.sop_class import ModalityWorklistInformationFind  # type: ignore[attr-defined]

from services.dicom.c_echo import CEcho
from services.dicom.c_store import CStore
from services.mwl.c_find import CFindHandler
from services.storage import PACSStorage, WorklistStorage

logger = logging.getLogger(__name__)


class PACSServer:
    """DICOM PACS Server with C-STORE support."""

    def __init__(
        self,
        ae_title: str = "SCREENING_PACS",
        port: int = 4244,
        storage_path: str = "/var/lib/pacs/storage",
        db_path: str = "/var/lib/pacs/pacs.db",
        block: bool = True,
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
        self.block = block

    def start(self):
        """Start the PACS server and listen for incoming connections."""
        logger.info(f"Starting PACS server: {self.ae_title} on port {self.port}")

        self.ae = AE(ae_title=self.ae_title)
        self.ae.supported_contexts = StoragePresentationContexts

        handlers = [(evt.EVT_C_ECHO, CEcho().call), (evt.EVT_C_STORE, CStore(self.storage).call)]

        logger.info(f"PACS server listening on 0.0.0.0:{self.port}")
        logger.info(f"Storage: {self.storage.storage_root}")
        logger.info(f"Database: {self.storage.db_path}")

        self.ae.start_server(("0.0.0.0", self.port), block=self.block, evt_handlers=handlers)  # type: ignore

    def stop(self):
        """Stop the PACS server."""
        if self.ae:
            logger.info("Stopping PACS server")
            self.ae.shutdown()
        self.storage.close()


class MWLServer:
    """DICOM Modality Worklist server with C-FIND support."""

    def __init__(
        self,
        ae_title: str = "MWL_SCP",
        port: int = 4243,
        db_path: str = "/var/lib/pacs/worklist.db",
        block: bool = True,
    ):
        """
        Initialize MWL server.

        Args:
            ae_title: Application Entity Title
            port: Port to listen on
            db_path: Path to SQLite worklist database
            block: Whether to block when starting server
        """
        self.ae_title = ae_title
        self.port = port
        self.storage = WorklistStorage(db_path)
        self.ae = None
        self.block = block

    def start(self):
        """Start the MWL server."""
        logger.info(f"Starting MWL server: {self.ae_title} on port {self.port}")

        self.ae = AE(ae_title=self.ae_title)
        self.ae.add_supported_context(ModalityWorklistInformationFind)

        handlers = [(evt.EVT_C_FIND, CFindHandler(self.storage).call)]

        logger.info(f"MWL server listening on 0.0.0.0:{self.port}")
        logger.info(f"Database: {self.storage.db_path}")

        self.ae.start_server(("0.0.0.0", self.port), block=self.block, evt_handlers=handlers)  # type: ignore

    def stop(self):
        """Stop the MWL server."""
        if self.ae:
            logger.info("Stopping MWL server")
            self.ae.shutdown()


def main():
    """Main entry point for PACS server."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
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
