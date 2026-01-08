"""Entry point for MWL server."""

import logging
import os

from server import MWLServer


def main():
    """Main entry point for MWL server."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )

    mwl_aet = os.getenv("MWL_AET", "MWL_SCP")
    mwl_port = int(os.getenv("MWL_PORT", "4243"))
    mwl_db_path = os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")

    mwl_server = MWLServer(mwl_aet, mwl_port, mwl_db_path, block=True)

    try:
        mwl_server.start()
    except KeyboardInterrupt:
        logging.info("Received shutdown signal")
        mwl_server.stop()


if __name__ == "__main__":
    main()
