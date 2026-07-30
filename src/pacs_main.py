"""Entry point for PACS server."""

import logging

from dotenv import load_dotenv

import config
from server import PACSServer
from telemetry import configure_telemetry

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
        level=config.log_level(),
        format=config.log_format(),
    )

    pacs_aet = config.pacs_aet()
    pacs_port = config.pacs_port()
    pacs_storage_path = config.pacs_storage_path()
    pacs_db_path = config.pacs_db_path()
    mwl_db_path = config.mwl_db_path()

    pacs_server = PACSServer(pacs_aet, pacs_port, pacs_storage_path, pacs_db_path, block=True, mwl_db_path=mwl_db_path)

    configure_telemetry(service_name="pacs-server")

    try:
        pacs_server.start()
    except KeyboardInterrupt:
        logging.info("Received shutdown signal")
        pacs_server.stop()


if __name__ == "__main__":
    main()
