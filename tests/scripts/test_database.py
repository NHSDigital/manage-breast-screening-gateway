import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.append(f"{Path(__file__).parent.parent.parent}/scripts/python")

from database import backup_database, reset_worklist_database


@pytest.fixture
def worklist_db(tmp_dir, monkeypatch):
    db_path = f"{tmp_dir}/test_worklist.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE worklist_items (accession_number TEXT PRIMARY KEY, patient_id TEXT)")
        conn.execute("INSERT INTO worklist_items VALUES ('ACC001', 'P001')")
        conn.execute("INSERT INTO worklist_items VALUES ('ACC002', 'P002')")
        conn.commit()

    monkeypatch.setenv("BACKUP_PATH", f"{tmp_dir}/backups")
    monkeypatch.setenv("MWL_DB_PATH", db_path)
    return db_path


# Tests for backup_database
def test_backup_creates_file(tmp_dir):
    """Backup creates file."""
    db_path = f"{tmp_dir}/test.db"
    sqlite3.connect(db_path).close()

    backup_path = backup_database(db_path, f"{tmp_dir}/backups")

    assert Path(backup_path).exists()


def test_backup_returns_timestamped_path(tmp_dir):
    """Backup returns timestamped path."""
    db_path = f"{tmp_dir}/test.db"
    sqlite3.connect(db_path).close()

    backup_path = backup_database(db_path, f"{tmp_dir}/backups")

    assert backup_path.endswith(".db.backup")


def test_backup_creates_backup_dir_if_missing(tmp_dir):
    """Backup creates backup dir if missing."""
    db_path = f"{tmp_dir}/test.db"
    sqlite3.connect(db_path).close()
    backup_dir = f"{tmp_dir}/backups/nested"

    backup_path = backup_database(db_path, backup_dir)

    assert Path(backup_path).exists()


def test_backup_database_creates_backup(worklist_db):
    """Backup database creates backup."""
    backup_path = backup_database(worklist_db, str(Path(worklist_db).parent / "backups"))
    assert Path(backup_path).exists()


# Tests for reset_worklist_database
def test_reset_worklist_database_deletes_all_rows(worklist_db):
    """Reset worklist database deletes all rows."""
    reset_worklist_database()

    with sqlite3.connect(worklist_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM worklist_items").fetchone()[0]
    assert count == 0


def test_reset_worklist_database_returns_row_count(worklist_db):
    """Reset worklist database returns row count."""
    assert reset_worklist_database() == 2


def test_reset_worklist_database_returns_zero_when_empty(tmp_dir, monkeypatch):
    """Reset worklist database returns zero when empty."""
    db_path = f"{tmp_dir}/worklist.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE worklist_items (accession_number TEXT PRIMARY KEY)")
        conn.commit()

    monkeypatch.setenv("MWL_DB_PATH", db_path)
    assert reset_worklist_database() == 0
