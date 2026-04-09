import sqlite3

import pytest

from mwl_clear import clear_worklist


@pytest.fixture
def worklist_db(tmp_path):
    db_path = str(tmp_path / "worklist.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE worklist_items (accession_number TEXT PRIMARY KEY, patient_id TEXT)")
        conn.execute("INSERT INTO worklist_items VALUES ('ACC001', 'P001')")
        conn.execute("INSERT INTO worklist_items VALUES ('ACC002', 'P002')")
        conn.commit()
    return db_path


def test_clear_worklist_deletes_all_rows(worklist_db):
    clear_worklist(worklist_db)

    with sqlite3.connect(worklist_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM worklist_items").fetchone()[0]
    assert count == 0


def test_clear_worklist_returns_row_count(worklist_db):
    assert clear_worklist(worklist_db) == 2


def test_clear_worklist_returns_zero_when_empty(tmp_path):
    db_path = str(tmp_path / "worklist.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE worklist_items (accession_number TEXT PRIMARY KEY)")
        conn.commit()

    assert clear_worklist(db_path) == 0
