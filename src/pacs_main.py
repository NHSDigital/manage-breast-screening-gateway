"""Entry point for PACS server."""

import os

from dotenv import load_dotenv

from server import PACSServer
from telemetry import configure_logging, configure_telemetry

load_dotenv()

logger = configure_logging("Gateway-PACS")


def main():
    """
    Main entry point for PACS server.

    Environment variables:
    PACS_AET: AE Title for the PACS server (default: SCREENING_PACS)
    PACS_PORT: Port to listen on (default: 4244)
    PACS_STORAGE_PATH: Path to store incoming DICOM files (default: /var/lib/pacs/storage)
    PACS_DB_PATH: Path to the SQLite database file (default: /var/lib/pacs/pacs.db)
    """
    pacs_aet = os.getenv("PACS_AET", "SCREENING_PACS")
    pacs_port = int(os.getenv("PACS_PORT", "4244"))
    pacs_storage_path = os.getenv("PACS_STORAGE_PATH", "/var/lib/pacs/storage")
    pacs_db_path = os.getenv("PACS_DB_PATH", "/var/lib/pacs/pacs.db")
    mwl_db_path = os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")

    pacs_server = PACSServer(
        ae_title=pacs_aet,
        port=pacs_port,
        storage_path=pacs_storage_path,
        db_path=pacs_db_path,
        logger=logger,
        block=True,
        mwl_db_path=mwl_db_path,
    )

    configure_telemetry(service_name="pacs-server")

    try:
        pacs_server.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        pacs_server.stop()


if __name__ == "__main__":
    main()
