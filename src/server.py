"""PACS and MWL DICOM Servers

Provides:
- C-STORE SCP (Service Class Provider) for receiving DICOM images (PACS)
- C-FIND SCP for modality worklist management (MWL)
"""

import logging
import os
import threading

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
    """Main entry point for PACS and MWL servers."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )

    # PACS configuration
    pacs_aet = os.getenv("PACS_AET", "SCREENING_PACS")
    pacs_port = int(os.getenv("PACS_PORT", "4244"))
    pacs_storage_path = os.getenv("PACS_STORAGE_PATH", "/var/lib/pacs/storage")
    pacs_db_path = os.getenv("PACS_DB_PATH", "/var/lib/pacs/pacs.db")

    # MWL configuration
    mwl_aet = os.getenv("MWL_AET", "MWL_SCP")
    mwl_port = int(os.getenv("MWL_PORT", "4243"))
    mwl_db_path = os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")

    # Create servers with block=True - each runs in its own thread so they won't block each other
    pacs_server = PACSServer(pacs_aet, pacs_port, pacs_storage_path, pacs_db_path, block=True)
    mwl_server = MWLServer(mwl_aet, mwl_port, mwl_db_path, block=True)

    # Start servers in separate threads
    pacs_thread = threading.Thread(target=pacs_server.start, name="PACSServer", daemon=True)
    mwl_thread = threading.Thread(target=mwl_server.start, name="MWLServer", daemon=True)

    pacs_thread.start()
    mwl_thread.start()

    logger.info("Both PACS and MWL servers started")

    try:
        # Keep main thread alive
        pacs_thread.join()
        mwl_thread.join()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        pacs_server.stop()
        mwl_server.stop()


if __name__ == "__main__":
    main()
