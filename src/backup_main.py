"""Entry point for backing up PACS and MWL databases."""

import logging
import os
import sys

from dotenv import load_dotenv

from db_backup import backup_database
from telemetry import configure_telemetry

load_dotenv()
configure_telemetry(service_name="backup")


def main():
    """
    Main entry point for database backup.

    Environment variables:
    PACS_DB_PATH:  Path to the PACS SQLite database
    MWL_DB_PATH:   Path to the MWL SQLite database
    BACKUP_PATH:   Directory for backups (default: ./backups)
    """
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )

    pacs_db_path = os.getenv("PACS_DB_PATH")
    mwl_db_path = os.getenv("MWL_DB_PATH")
    backup_path = os.getenv("BACKUP_PATH", "./backups")

    success = True

    if pacs_db_path:
        try:
            backup_database(pacs_db_path, backup_path)
        except Exception as e:
            logging.error(f"PACS backup failed: {e}")
            success = False
    else:
        logging.info("PACS_DB_PATH not set, skipping PACS backup")

    if mwl_db_path:
        try:
            backup_database(mwl_db_path, backup_path)
        except Exception as e:
            logging.error(f"MWL backup failed: {e}")
            success = False
    else:
        logging.info("MWL_DB_PATH not set, skipping MWL backup")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
