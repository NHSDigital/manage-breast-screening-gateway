import sqlite3
from pathlib import Path

from db_backup import backup_database


def test_backup_creates_file(tmp_path):
    db_path = str(tmp_path / "test.db")
    sqlite3.connect(db_path).close()

    backup_path = backup_database(db_path, str(tmp_path / "backups"))

    assert Path(backup_path).exists()


def test_backup_returns_timestamped_path(tmp_path):
    db_path = str(tmp_path / "test.db")
    sqlite3.connect(db_path).close()

    backup_path = backup_database(db_path, str(tmp_path / "backups"))

    assert backup_path.endswith(".db.backup")


def test_backup_creates_backup_dir_if_missing(tmp_path):
    db_path = str(tmp_path / "test.db")
    sqlite3.connect(db_path).close()
    backup_dir = str(tmp_path / "backups" / "nested")

    backup_path = backup_database(db_path, backup_dir)

    assert Path(backup_path).exists()
