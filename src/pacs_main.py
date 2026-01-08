"""Entry point for PACS server."""

import logging
import os

from server import PACSServer


def main():
    """Main entry point for PACS server."""
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
