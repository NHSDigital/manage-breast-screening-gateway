"""Delete test worklist items and stored instances from a gateway.

Usage:

    PYTHONPATH=src uv run python scripts/python/cleanup_test_data.py

Exit codes: 0 = clean, 1 = deletion ran but test data remains (investigate),
2 = refused because non-test uploads are pending (buffer not drained).
"""

import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
)
logger = logging.getLogger(__name__)

# ADR-007 test accessions: "TEST" + yymmddHHMM + 2 uppercase hex chars.
TEST_ACCESSION_RE = re.compile(r"^TEST\d{10}[0-9A-F]{2}$")

SETTLED_UPLOAD_STATUSES = ("COMPLETE", "FAILED")
IN_FLIGHT_UPLOAD_STATUSES = ("PENDING", "UPLOADING")

EXIT_CLEAN = 0
EXIT_RESIDUE_REMAINS = 1
EXIT_UPLOADS_PENDING = 2


def is_test_accession(accession_number: str | None) -> bool:
    return bool(accession_number and TEST_ACCESSION_RE.match(accession_number))


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def count_non_test_in_flight(pacs_conn: sqlite3.Connection) -> int:
    """Non-test instances awaiting upload."""
    rows = pacs_conn.execute(
        "SELECT accession_number FROM stored_instances WHERE upload_status IN (?, ?)",
        IN_FLIGHT_UPLOAD_STATUSES,
    ).fetchall()
    return sum(1 for row in rows if not is_test_accession(row["accession_number"]))


def find_test_worklist_items(mwl_conn: sqlite3.Connection) -> list[str]:
    rows = mwl_conn.execute(
        "SELECT accession_number FROM worklist_items WHERE accession_number LIKE 'TEST%'"
    ).fetchall()
    return [row["accession_number"] for row in rows if is_test_accession(row["accession_number"])]


def find_test_instances(pacs_conn: sqlite3.Connection) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    rows = pacs_conn.execute(
        "SELECT sop_instance_uid, accession_number, storage_path, upload_status "
        "FROM stored_instances WHERE accession_number LIKE 'TEST%'"
    ).fetchall()
    test_rows = [row for row in rows if is_test_accession(row["accession_number"])]
    deletable = [row for row in test_rows if row["upload_status"] in SETTLED_UPLOAD_STATUSES]
    in_flight = [row for row in test_rows if row["upload_status"] not in SETTLED_UPLOAD_STATUSES]
    return deletable, in_flight


def delete_instance_file(storage_root: str, storage_path: str) -> bool:
    """Delete a stored DICOM file."""
    file_path = Path(storage_root) / storage_path
    if not file_path.is_file():
        logger.warning("File missing on disk (row will still be deleted): %s", file_path)
        return False
    file_path.unlink()
    # Best-effort prune of the ab/cd hash directories if now empty.
    for parent in [file_path.parent, file_path.parent.parent]:
        try:
            if parent != Path(storage_root) and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            break
    return True


def cleanup(mwl_db_path: str, pacs_db_path: str, storage_root: str) -> int:
    """Run the cleanup. Returns a process exit code."""
    logger.info("Test-data cleanup starting")

    with _connect(pacs_db_path) as pacs_conn, _connect(mwl_db_path) as mwl_conn:
        blocking = count_non_test_in_flight(pacs_conn)
        if blocking:
            logger.error(
                "%d non-test instance(s) are awaiting upload, hence not running this task.",
                blocking,
            )
            return EXIT_UPLOADS_PENDING

        worklist_accessions = find_test_worklist_items(mwl_conn)
        deletable, in_flight = find_test_instances(pacs_conn)

        if in_flight:
            logger.warning(
                "Skipping %d test instance(s) still mid-upload",
                len(in_flight),
            )

        if not worklist_accessions and not deletable:
            logger.info("Nothing to clean up.")
            return EXIT_CLEAN

        files_deleted = 0
        for row in deletable:
            if delete_instance_file(storage_root, row["storage_path"]):
                files_deleted += 1
            pacs_conn.execute(
                "DELETE FROM stored_instances WHERE sop_instance_uid = ?",
                (row["sop_instance_uid"],),
            )
        pacs_conn.commit()

        for accession in worklist_accessions:
            mwl_conn.execute("DELETE FROM worklist_items WHERE accession_number = ?", (accession,))
        mwl_conn.commit()

        remaining_worklist = len(find_test_worklist_items(mwl_conn))
        remaining_instances = len(find_test_instances(pacs_conn)[0])
        logger.info(
            "Deleted: %d worklist item(s), %d stored instance row(s), %d file(s).",
            len(worklist_accessions),
            len(deletable),
            files_deleted,
        )
        logger.info(
            "Verification - remaining settled test data: %d worklist item(s), %d instance(s).",
            remaining_worklist,
            remaining_instances,
        )
        if remaining_worklist == 0 and remaining_instances == 0:
            return EXIT_CLEAN
        return EXIT_RESIDUE_REMAINS


def main() -> int:
    import config

    return cleanup(
        mwl_db_path=config.mwl_db_path(),
        pacs_db_path=config.pacs_db_path(),
        storage_root=config.pacs_storage_path(),
    )


if __name__ == "__main__":
    sys.exit(main())
