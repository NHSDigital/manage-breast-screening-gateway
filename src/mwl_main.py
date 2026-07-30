"""Entry point for MWL server."""

import logging

from dotenv import load_dotenv

import config
from server import MWLServer
from telemetry import configure_telemetry

load_dotenv()


def main():
    """
    Main entry point for MWL server.

    Environment variables:
    MWL_AET: AE Title for the MWL server (default: MWL_SCP)
    MWL_PORT: Port to listen on (default: 4243)
    MWL_DB_PATH: Path to the SQLite database file (default: /var/lib/pacs/worklist.db)
    """
    logging.basicConfig(
        level=config.log_level(),
        format=config.log_format(),
    )

    mwl_aet = config.mwl_aet()
    mwl_port = config.mwl_port()
    mwl_db_path = config.mwl_db_path()

    mwl_server = MWLServer(mwl_aet, mwl_port, mwl_db_path, block=True)

    configure_telemetry(service_name="mwl-server")

    try:
        mwl_server.start()
    except KeyboardInterrupt:
        logging.info("Received shutdown signal")
        mwl_server.stop()


if __name__ == "__main__":
    main()
