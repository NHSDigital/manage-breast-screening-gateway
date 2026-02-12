"""Entry point for PACS server."""

import logging
import os

from dotenv import load_dotenv

from server import PACSServer

load_dotenv()


def main():
    """
    Main entry point for PACS server.

    Environment variables:
    PACS_AET: AE Title for the PACS server (default: SCREENING_PACS)
    PACS_PORT: Port to listen on (default: 4244)
    PACS_STORAGE_PATH: Path to store incoming DICOM files (default: /var/lib/pacs/storage)
    PACS_DB_PATH: Path to the SQLite database file (default: /var/lib/pacs/pacs.db)
    """
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )

    pacs_aet = os.getenv("PACS_AET", "SCREENING_PACS")
    pacs_port = int(os.getenv("PACS_PORT", "4244"))
    pacs_storage_path = os.getenv("PACS_STORAGE_PATH", "/var/lib/pacs/storage")
    pacs_db_path = os.getenv("PACS_DB_PATH", "/var/lib/pacs/pacs.db")

    pacs_server = PACSServer(pacs_aet, pacs_port, pacs_storage_path, pacs_db_path, block=True)

    try:
        pacs_server.start()
    except KeyboardInterrupt:
        logging.info("Received shutdown signal")
        pacs_server.stop()


if __name__ == "__main__":
    main()
