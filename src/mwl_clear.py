import sqlite3


def clear_worklist(db_path: str) -> int:
    """Delete all rows from worklist_items. Returns the number of rows deleted."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM worklist_items")
        conn.commit()
        return cursor.rowcount
