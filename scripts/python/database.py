import logging
import os
import sqlite3

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format=os.getenv(
        "LOG_FORMAT",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    ),
)
logger = logging.getLogger(__name__)


MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", 5))


def backup_db_path(db_path: str, backup_dir: str) -> str:
    """
    Returns the path of the newest backup file (.backup.0).
    """
    os.makedirs(backup_dir, exist_ok=True)
    db_filename = os.path.basename(db_path)
    return os.path.join(backup_dir, f"{db_filename}.backup.0")


def rotate_backups(backup_dir: str, db_filename: str) -> None:
    """
    Keep exactly MAX_BACKUPS backups:
        backup.0 (newest)
        backup.1
        backup.2
        backup.3
        backup.4 (oldest)

    Before creating a new backup, rotate existing files upward.
    """
    # Remove the oldest backup first
    oldest = os.path.join(
        backup_dir,
        f"{db_filename}.backup.{MAX_BACKUPS - 1}",
    )
    if os.path.exists(oldest):
        os.remove(oldest)
        logger.info("Deleted oldest backup: %s", oldest)

    # Rotate existing backups upward
    for i in range(MAX_BACKUPS - 2, -1, -1):
        src = os.path.join(backup_dir, f"{db_filename}.backup.{i}")
        dst = os.path.join(backup_dir, f"{db_filename}.backup.{i + 1}")

        if os.path.exists(src):
            os.rename(src, dst)
            logger.info("Rotated backup: %s -> %s", src, dst)


def backup_and_reset() -> int:
    """
    Backup and reset a SQLite database.

    Returns the number of rows deleted.
    """
    db_path = os.getenv("DB_PATH")
    if not db_path:
        logger.warning("DB_PATH not set, skipping database reset")
        return 0

    table_name = os.getenv("TABLE_NAME")
    if table_name not in {"stored_instances", "worklist_items"}:
        logger.warning(
            "Invalid TABLE_NAME '%s' specified, skipping database reset",
            table_name,
        )
        return 0

    backup_dir = os.getenv("BACKUP_PATH", "./backups")
    db_filename = os.path.basename(db_path)

    # Rotate existing backups before creating the new one
    rotate_backups(backup_dir, db_filename)

    backup_path = backup_db_path(db_path, backup_dir)

    count = 0

    try:
        with sqlite3.connect(db_path) as conn:
            with sqlite3.connect(backup_path) as backup_conn:
                conn.backup(backup_conn)

            logger.info("Database backup complete: %s", backup_path)

            cursor = conn.execute(f"DELETE FROM {table_name}")
            conn.commit()
            count = cursor.rowcount

            logger.info(
                "Database reset complete: %s items deleted from %s",
                count,
                table_name,
            )

            backup_conn.close()
        conn.close()

        return count

    except Exception:
        logger.exception("Database reset failed")
        raise


if __name__ == "__main__":
    deleted = backup_and_reset()
    logger.info("Total rows deleted: %d", deleted)
    exit(0)
