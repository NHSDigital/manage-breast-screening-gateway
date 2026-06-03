import logging
import os
import sqlite3
from datetime import datetime

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
)
logger = logging.getLogger(__name__)


def backup_database(db_path: str, backup_dir: str) -> str:
    """
    Backup a SQLite database to a timestamped file in backup_dir.

    Returns the path of the backup file.
    """
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    db_filename = os.path.basename(db_path)
    backup_path = os.path.join(backup_dir, f"{timestamp}.{db_filename}.backup")
    with sqlite3.connect(db_path) as conn:
        with sqlite3.connect(backup_path) as backup_conn:
            conn.backup(backup_conn)
    return backup_path


def backup_databases():
    """
    Backup all configured databases.

    Environment variables:
    PACS_DB_PATH:  Path to the PACS SQLite database
    MWL_DB_PATH:   Path to the MWL SQLite database
    BACKUP_PATH:   Directory for backups (default: ./backups)
    """
    pacs_db_path = os.getenv("PACS_DB_PATH")
    mwl_db_path = os.getenv("MWL_DB_PATH")
    backup_path = os.getenv("BACKUP_PATH", "./backups")

    if not pacs_db_path and not mwl_db_path:
        logger.warning("No database paths configured (PACS_DB_PATH or MWL_DB_PATH), skipping backup")
        return

    success = True

    if pacs_db_path:
        try:
            pacs_backup_path = backup_database(pacs_db_path, backup_path)
        except Exception as e:
            logging.error(f"PACS backup failed: {e}")
            success = False
    else:
        logging.info("PACS_DB_PATH not set, skipping PACS backup")

    if mwl_db_path:
        try:
            mwl_backup_path = backup_database(mwl_db_path, backup_path)
        except Exception as e:
            logging.error(f"MWL backup failed: {e}")
            success = False
    else:
        logging.info("MWL_DB_PATH not set, skipping MWL backup")

    if success:
        logger.info("All database backups completed successfully. Backup files:")
        if pacs_db_path:
            logger.info(f"  PACS backup: {pacs_backup_path}")
        if mwl_db_path:
            logger.info(f"  MWL backup: {mwl_backup_path}")


def reset_worklist_database() -> int:
    """
    Backs up and clears the MWL database..

    Environment variables:
    MWL_DB_PATH:  Path to the MWL SQLite database (default: /var/lib/pacs/worklist.db)
    BACKUP_PATH:  Directory for database backups (default: /var/lib/pacs/backups)
    """
    mwl_db_path = os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")
    backup_path = os.getenv("BACKUP_PATH", "/var/lib/pacs/backups")
    count = 0

    try:
        path = backup_database(mwl_db_path, backup_path)
        logger.info(f"Backup complete: {path}")
    except Exception as e:
        logger.error(f"MWL backup failed: {e}", exc_info=True)

    try:
        with sqlite3.connect(mwl_db_path) as conn:
            cursor = conn.execute("DELETE FROM worklist_items")
            conn.commit()
            count = cursor.rowcount
            logger.info(f"MWL reset complete: {count} items deleted")
    except Exception as e:
        logger.error(f"MWL clear failed: {e}", exc_info=True)

    return count
