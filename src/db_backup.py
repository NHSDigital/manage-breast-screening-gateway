import os
import sqlite3
from datetime import datetime


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
