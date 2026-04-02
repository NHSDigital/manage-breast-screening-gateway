"""Entry point for MWL daily backup and reset scheduler."""

import logging
import os

from dotenv import load_dotenv

from services.mwl.reset import MWLResetScheduler
from services.storage import MWLStorage
from telemetry import configure_telemetry

load_dotenv()
configure_telemetry(service_name="reset")


def main():
    """
    Main entry point for MWL reset scheduler.

    Environment variables:
    MWL_DB_PATH:        Path to the MWL SQLite database (default: /var/lib/pacs/worklist.db)
    BACKUP_PATH:        Directory for database backups (default: /var/lib/pacs/backups)
    MWL_RESET_SCHEDULE: Cron expression for reset schedule in UTC (default: 0 2 * * * — daily at 02:00)
    """
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )

    mwl_db_path = os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")
    backup_path = os.getenv("BACKUP_PATH", "/var/lib/pacs/backups")
    reset_schedule = os.getenv("MWL_RESET_SCHEDULE", "0 2 * * *")

    mwl_storage = MWLStorage(mwl_db_path)
    scheduler = MWLResetScheduler(mwl_storage, backup_path, reset_schedule)

    try:
        scheduler.run()
    except KeyboardInterrupt:
        logging.info("Received shutdown signal")


if __name__ == "__main__":
    main()
