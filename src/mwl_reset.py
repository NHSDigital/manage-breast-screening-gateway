"""MWL backup and reset script. Intended to be invoked by Windows Task Scheduler (or equivalent)."""

import logging
import os
import sys

from dotenv import load_dotenv

from db_backup import backup_database
from mwl_clear import clear_worklist
from telemetry import configure_telemetry

load_dotenv()
configure_telemetry(service_name="mwl_reset")


def main():
    """
    Backs up and clears the MWL database. Exits with code 1 if the clear fails.

    Environment variables:
    MWL_DB_PATH:  Path to the MWL SQLite database (default: /var/lib/pacs/worklist.db)
    BACKUP_PATH:  Directory for database backups (default: /var/lib/pacs/backups)
    """
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )
    logger = logging.getLogger(__name__)

    mwl_db_path = os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")
    backup_path = os.getenv("BACKUP_PATH", "/var/lib/pacs/backups")

    try:
        path = backup_database(mwl_db_path, backup_path)
        logger.info(f"Backup complete: {path}")
    except Exception as e:
        logger.error(f"MWL backup failed: {e}", exc_info=True)

    try:
        count = clear_worklist(mwl_db_path)
        logger.info(f"MWL reset complete: {count} items deleted")
    except Exception as e:
        logger.error(f"MWL clear failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
