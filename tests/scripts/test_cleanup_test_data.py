import sys
from pathlib import Path

import pytest

sys.path.append(f"{Path(__file__).parent.parent.parent}/scripts/python")

from cleanup_test_data import (
    EXIT_CLEAN,
    EXIT_UPLOADS_PENDING,
    cleanup,
    is_test_accession,
)

from models import WorklistItem
from services.storage import MWLStorage, PACSStorage

TEST_ACCESSION = "TEST2610051030AB"
OTHER_TEST_ACCESSION = "TEST2610051031CD"
REAL_ACCESSION = "ACC123456"


@pytest.fixture
def paths(tmp_path):
    return {
        "mwl_db": str(tmp_path / "worklist.db"),
        "pacs_db": str(tmp_path / "pacs.db"),
        "storage": str(tmp_path / "storage"),
    }


@pytest.fixture
def mwl(paths):
    return MWLStorage(paths["mwl_db"])


@pytest.fixture
def pacs(paths):
    return PACSStorage(paths["pacs_db"], paths["storage"])


def insert_worklist_item(mwl, accession):
    mwl.store_worklist_item(
        WorklistItem(
            accession_number=accession,
            modality="MG",
            patient_birth_date="19900101",
            patient_id="9991112223",
            patient_name="TEST^PATIENT",
            scheduled_date="20261005",
            scheduled_time="090000",
        )
    )


def insert_instance(pacs, accession, sop_uid, upload_status, with_file=True):
    """Store an instance through the real PACS API, then walk it to the
    requested upload state via the mark_upload_* lifecycle."""
    pacs.store_instance(sop_uid, b"DICM-test", {"accession_number": accession})
    storage_path = instance_storage_path(pacs, sop_uid)
    if not with_file:
        (Path(pacs.storage_root) / storage_path).unlink()
    if upload_status == "UPLOADING":
        pacs.mark_upload_started(sop_uid)
    elif upload_status == "COMPLETE":
        pacs.mark_upload_complete(sop_uid)
    elif upload_status == "FAILED":
        pacs.mark_upload_failed(sop_uid, "test failure", permanent=True)
    return storage_path


def instance_storage_path(pacs, sop_uid):
    with pacs._get_connection() as conn:
        row = conn.execute(
            "SELECT storage_path FROM stored_instances WHERE sop_instance_uid = ?",
            (sop_uid,),
        ).fetchone()
    return row["storage_path"]


def instance_count(pacs, accession):
    with pacs._get_connection() as conn:
        row = conn.execute(
            "SELECT count(*) AS n FROM stored_instances WHERE accession_number = ?",
            (accession,),
        ).fetchone()
    return row["n"]


def worklist_count(mwl, accession):
    with mwl._get_connection() as conn:
        row = conn.execute(
            "SELECT count(*) AS n FROM worklist_items WHERE accession_number = ?",
            (accession,),
        ).fetchone()
    return row["n"]


class TestIsTestAccession:
    def test_matches_adr007_format(self):
        assert is_test_accession("TEST2610051030AB")

    def test_rejects_prefix_only_lookalikes(self):
        assert not is_test_accession("TESTING123")
        assert not is_test_accession("TEST123")  # too short
        assert not is_test_accession("TEST2610051030ab")  # lowercase hex
        assert not is_test_accession("TEST2610051030ABX")  # too long
        assert not is_test_accession(None)
        assert not is_test_accession("")


class TestDelete:
    def test_deletes_test_rows_and_files_leaves_real_data(self, mwl, pacs, paths):
        insert_worklist_item(mwl, TEST_ACCESSION)
        insert_worklist_item(mwl, REAL_ACCESSION)
        test_path = insert_instance(pacs, TEST_ACCESSION, "1.2.3", "FAILED")
        real_path = insert_instance(pacs, REAL_ACCESSION, "4.5.6", "COMPLETE")

        exit_code = cleanup(paths["mwl_db"], paths["pacs_db"], paths["storage"])

        assert exit_code == EXIT_CLEAN
        assert worklist_count(mwl, TEST_ACCESSION) == 0
        assert instance_count(pacs, TEST_ACCESSION) == 0
        assert not (Path(paths["storage"]) / test_path).exists()
        # Real data untouched
        assert worklist_count(mwl, REAL_ACCESSION) == 1
        assert instance_count(pacs, REAL_ACCESSION) == 1
        assert (Path(paths["storage"]) / real_path).is_file()

    def test_prefix_lookalike_accession_is_not_deleted(self, mwl, pacs, paths):
        insert_worklist_item(mwl, "TESTING123")

        exit_code = cleanup(paths["mwl_db"], paths["pacs_db"], paths["storage"])

        assert exit_code == EXIT_CLEAN
        assert worklist_count(mwl, "TESTING123") == 1

    def test_missing_file_still_deletes_row(self, mwl, pacs, paths):
        insert_instance(pacs, TEST_ACCESSION, "1.2.3", "COMPLETE", with_file=False)

        exit_code = cleanup(paths["mwl_db"], paths["pacs_db"], paths["storage"])

        assert exit_code == EXIT_CLEAN
        assert instance_count(pacs, TEST_ACCESSION) == 0


class TestPendingUploadsGuard:
    def test_refuses_when_non_test_instance_awaits_upload(self, mwl, pacs, paths):
        insert_worklist_item(mwl, TEST_ACCESSION)
        insert_instance(pacs, TEST_ACCESSION, "1.2.3", "COMPLETE")
        insert_instance(pacs, REAL_ACCESSION, "4.5.6", "PENDING")

        exit_code = cleanup(paths["mwl_db"], paths["pacs_db"], paths["storage"])

        assert exit_code == EXIT_UPLOADS_PENDING
        # Nothing deleted at all
        assert worklist_count(mwl, TEST_ACCESSION) == 1
        assert instance_count(pacs, TEST_ACCESSION) == 1

    def test_in_flight_test_instance_is_skipped_not_deleted(self, mwl, pacs, paths):
        in_flight_path = insert_instance(pacs, TEST_ACCESSION, "1.2.3", "UPLOADING")
        insert_instance(pacs, OTHER_TEST_ACCESSION, "4.5.6", "COMPLETE")

        exit_code = cleanup(paths["mwl_db"], paths["pacs_db"], paths["storage"])

        assert exit_code == EXIT_CLEAN
        assert instance_count(pacs, TEST_ACCESSION) == 1
        assert (Path(paths["storage"]) / in_flight_path).is_file()
        assert instance_count(pacs, OTHER_TEST_ACCESSION) == 0
