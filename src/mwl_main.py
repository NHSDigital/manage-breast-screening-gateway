"""Entry point for MWL server."""

import os

from dotenv import load_dotenv

from server import MWLServer
from telemetry import configure_logging, configure_telemetry

load_dotenv()

logger = configure_logging("Gateway-MWL")


def main():
    """
    Main entry point for MWL server.

    Environment variables:
    MWL_AET: AE Title for the MWL server (default: MWL_SCP)
    MWL_PORT: Port to listen on (default: 4243)
    MWL_DB_PATH: Path to the SQLite database file (default: /var/lib/pacs/worklist.db)
    """
    mwl_aet = os.getenv("MWL_AET", "MWL_SCP")
    mwl_port = int(os.getenv("MWL_PORT", "4243"))
    mwl_db_path = os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")

    mwl_server = MWLServer(
        ae_title=mwl_aet,
        port=mwl_port,
        db_path=mwl_db_path,
        logger=logger,
        block=True,
    )

    configure_telemetry(service_name="mwl-server")

    try:
        mwl_server.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        mwl_server.stop()


if __name__ == "__main__":
    main()
