import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.append(f"{Path(__file__).parent.parent.parent}/scripts/python")

from database import (
    backup_and_reset,
)


@pytest.fixture
def sqlite_db(tmp_path):
    db_path = tmp_path / "test.db"

    conn = sqlite3.connect(db_path)

    conn.execute(
        """
        CREATE TABLE stored_instances (
            id INTEGER PRIMARY KEY,
            value TEXT
        )
        """
    )

    conn.executemany(
        "INSERT INTO stored_instances(value) VALUES (?)",
        [("a",), ("b",), ("c",)],
    )

    conn.commit()
    conn.close()

    return db_path


def row_count(db_path, table):
    conn = sqlite3.connect(db_path)
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.close()
    return count


def test_backup_and_reset_creates_backup(
    tmp_path,
    sqlite_db,
    monkeypatch,
):
    """Backup database creates backup."""
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("DB_PATH", str(sqlite_db))
    monkeypatch.setenv("TABLE_NAME", "stored_instances")
    monkeypatch.setenv("BACKUP_PATH", str(backup_dir))
    monkeypatch.setenv("MAX_BACKUPS", "5")

    deleted = backup_and_reset()

    assert deleted == 3

    backup_file = backup_dir / "test.db.backup.0"
    assert backup_file.exists()

    # Original DB was cleared
    assert row_count(sqlite_db, "stored_instances") == 0

    # Backup still contains original rows
    assert row_count(backup_file, "stored_instances") == 3


def test_rotation_keeps_five_backups(
    tmp_path,
    sqlite_db,
    monkeypatch,
):
    """Only 5 database backups are kept and older ones are deleted."""
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("DB_PATH", str(sqlite_db))
    monkeypatch.setenv("TABLE_NAME", "stored_instances")
    monkeypatch.setenv("BACKUP_PATH", str(backup_dir))
    monkeypatch.setenv("MAX_BACKUPS", "5")

    # Generate 7 backups
    for i in range(7):
        conn = sqlite3.connect(sqlite_db)
        conn.execute(
            "INSERT INTO stored_instances(value) VALUES (?)",
            (f"run-{i}",),
        )
        conn.commit()
        conn.close()

        backup_and_reset()

    backups = sorted(backup_dir.glob("test.db.backup.*"))

    assert len(backups) == 5

    expected = {
        "test.db.backup.0",
        "test.db.backup.1",
        "test.db.backup.2",
        "test.db.backup.3",
        "test.db.backup.4",
    }

    assert {p.name for p in backups} == expected


def test_newest_backup_is_backup_zero(
    tmp_path,
    sqlite_db,
    monkeypatch,
):
    """Newest backup is always backup.0."""
    backup_dir = tmp_path / "backups"

    monkeypatch.setenv("DB_PATH", str(sqlite_db))
    monkeypatch.setenv("TABLE_NAME", "stored_instances")
    monkeypatch.setenv("BACKUP_PATH", str(backup_dir))
    monkeypatch.setenv("MAX_BACKUPS", "5")

    # First backup contains 3 rows
    backup_and_reset()

    # Add one row and create another backup
    conn = sqlite3.connect(sqlite_db)
    conn.execute("INSERT INTO stored_instances(value) VALUES ('new')")
    conn.commit()
    conn.close()

    backup_and_reset()

    newest = backup_dir / "test.db.backup.0"
    previous = backup_dir / "test.db.backup.1"

    assert row_count(newest, "stored_instances") == 1
    assert row_count(previous, "stored_instances") == 3


def test_invalid_table_name_is_ignored(
    tmp_path,
    sqlite_db,
    monkeypatch,
):
    """Invalid table name is ignored."""
    backup_dir = tmp_path / "backups"

    monkeypatch.setenv("DB_PATH", str(sqlite_db))
    monkeypatch.setenv("TABLE_NAME", "users")
    monkeypatch.setenv("BACKUP_PATH", str(backup_dir))

    result = backup_and_reset()

    assert result == 0
    assert not backup_dir.exists()


def test_missing_db_path_is_ignored(
    monkeypatch,
):
    """Missing DB_PATH is ignored."""
    monkeypatch.delenv("DB_PATH", raising=False)

    result = backup_and_reset()

    assert result == 0
