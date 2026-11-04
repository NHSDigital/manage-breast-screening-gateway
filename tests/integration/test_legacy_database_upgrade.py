"""
Integration-style tests for the upgrade of databases created by the legacy
initialisation mechanism.

Databases created by the legacy mechanism hold the schema and their data, but
have a user_version of 0. The migration runner must bring them up to the
current version without re-initialising the schema, so that the existing
records are left untouched.
"""

import shutil
import sqlite3
from pathlib import Path

import pytest
from pydicom.uid import generate_uid

from services.storage import MWLStorage, PACSStorage

# Schemas as created by the legacy initialisation mechanism, before database
# migrations were introduced. The old Storage._ensure_db() executed these
# scripts directly, and did not set the user_version pragma, so databases
# created before the pragma was introduced hold the schema and their data,
# but with user_version = 0.
ROOT_DIR = Path(__file__).parent.parent.parent
LEGACY_PACS_SCHEMA = open(f"{ROOT_DIR}/src/database/pacs/001_initial_schema.sql").read()
LEGACY_WORKLIST_SCHEMA = open(f"{ROOT_DIR}/src/database/worklist/001_initial_schema.sql").read()

# Identifiers for the records held in a database created by the legacy
# mechanism. They are generated rather than hardcoded, so that they are always
# valid UIDs and unique.
# This also prevents false positive gitleaks errors.
LEGACY_PACS_SOP_INSTANCE_UID = generate_uid()
LEGACY_PACS_SECOND_SOP_INSTANCE_UID = generate_uid()
LEGACY_WORKLIST_STUDY_INSTANCE_UID = generate_uid()
LEGACY_WORKLIST_MPPS_INSTANCE_UID = generate_uid()
NEW_SOP_INSTANCE_UID = generate_uid()

# Representative records held in a database created by the legacy mechanism
LEGACY_PACS_INSTANCES = [
    {
        "sop_instance_uid": LEGACY_PACS_SOP_INSTANCE_UID,
        "storage_path": "ab/cd/abcdef0123456789.dcm",
        "file_size": 2048,
        "storage_hash": "a" * 64,
        "patient_id": "999123456",
        "patient_name": "SMITH^JANE",
        "accession_number": "ACC123456",
        "status": "STORED",
        "upload_status": "PENDING",
        "upload_attempt_count": 0,
        "last_upload_attempt": None,
        "uploaded_at": None,
        "source_aet": "MODALITY1",
    },
    {
        "sop_instance_uid": LEGACY_PACS_SECOND_SOP_INSTANCE_UID,
        "storage_path": "ef/01/ef0123456789abcd.dcm",
        "file_size": 4096,
        "storage_hash": "b" * 64,
        "patient_id": "999654321",
        "patient_name": "BROWN^JOHN",
        "accession_number": "ACC654321",
        "status": "STORED",
        "upload_status": "COMPLETE",
        "upload_attempt_count": 1,
        "last_upload_attempt": "2026-01-02 09:15:00",
        "uploaded_at": "2026-01-02 09:16:00",
        "source_aet": "MODALITY2",
    },
]

LEGACY_WORKLIST_ITEMS = [
    {
        "accession_number": "ACC123456",
        "patient_id": "999123456",
        "patient_name": "SMITH^JANE",
        "patient_birth_date": "19800101",
        "patient_sex": "F",
        "scheduled_date": "20240101",
        "scheduled_time": "090000",
        "modality": "MG",
        "study_description": "MAMMOGRAPHY",
        "procedure_code": "12345-6",
        "status": "SCHEDULED",
        "study_instance_uid": None,
        "mpps_instance_uid": None,
        "source_message_id": "MSGID123456",
    },
    {
        "accession_number": "ACC654321",
        "patient_id": "999654321",
        "patient_name": "BROWN^JOHN",
        "patient_birth_date": "19751212",
        "patient_sex": "F",
        "scheduled_date": "20240102",
        "scheduled_time": "101500",
        "modality": "MG",
        "study_description": "MAMMOGRAPHY",
        "procedure_code": "12345-6",
        "status": "IN PROGRESS",
        "study_instance_uid": LEGACY_WORKLIST_STUDY_INSTANCE_UID,
        "mpps_instance_uid": LEGACY_WORKLIST_MPPS_INSTANCE_UID,
        "source_message_id": "MSGID654321",
    },
]


@pytest.fixture
def db_file(tmp_dir):
    return tmp_dir / "test.db"


@pytest.fixture
def legacy_pacs_db(db_file):
    """Create a PACS database using the legacy initialisation mechanism.

    The schema is created directly from the legacy schema, and the data is
    inserted before the storage is constructed. The user_version pragma is
    left at 0, as it was for databases created before the pragma existed.
    """
    conn = sqlite3.connect(db_file)
    conn.executescript(LEGACY_PACS_SCHEMA)
    conn.executemany(
        "INSERT INTO stored_instances (sop_instance_uid, storage_path, file_size, storage_hash, "
        "patient_id, patient_name, accession_number, status, upload_status, upload_attempt_count, "
        "last_upload_attempt, uploaded_at, source_aet) "
        "VALUES (:sop_instance_uid, :storage_path, :file_size, :storage_hash, :patient_id, "
        ":patient_name, :accession_number, :status, :upload_status, :upload_attempt_count, "
        ":last_upload_attempt, :uploaded_at, :source_aet)",
        LEGACY_PACS_INSTANCES,
    )
    conn.commit()
    conn.close()

    return db_file


@pytest.fixture
def legacy_worklist_db(db_file):
    """Create a worklist database using the legacy initialisation mechanism.

    The schema is created directly from the legacy schema, and the data is
    inserted before the storage is constructed. The user_version pragma is
    left at 0, as it was for databases created before the pragma existed.
    """
    conn = sqlite3.connect(db_file)
    conn.executescript(LEGACY_WORKLIST_SCHEMA)
    conn.executemany(
        "INSERT INTO worklist_items (accession_number, patient_id, patient_name, patient_birth_date, "
        "patient_sex, scheduled_date, scheduled_time, modality, study_description, procedure_code, "
        "status, study_instance_uid, mpps_instance_uid, source_message_id) "
        "VALUES (:accession_number, :patient_id, :patient_name, :patient_birth_date, :patient_sex, "
        ":scheduled_date, :scheduled_time, :modality, :study_description, :procedure_code, :status, "
        ":study_instance_uid, :mpps_instance_uid, :source_message_id)",
        LEGACY_WORKLIST_ITEMS,
    )
    conn.commit()
    conn.close()

    return db_file


@pytest.mark.integration
class TestLegacyDatabaseUpgrade:
    """Upgrade of databases created by the legacy initialisation mechanism.

    Databases created by the legacy mechanism hold the schema and their data,
    but have a user_version of 0. The migration runner must bring them up to
    the current version without re-initialising the schema, so that the
    existing records are left untouched.
    """

    def _user_version(self, db_path):
        conn = sqlite3.connect(db_path)
        try:
            return conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()

    def _rows(self, db_path, table, order_by):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order_by}").fetchall()]
        finally:
            conn.close()

    def test_pacs_legacy_database_is_upgraded(self, legacy_pacs_db, tmp_dir, monkeypatch):
        """PACS storage: Populated legacy database is upgraded to version 1."""
        monkeypatch.setattr(PACSStorage, "migrations_path", tmp_dir)
        shutil.copy(
            f"{pytest.root_dir}/src/database/pacs/001_initial_schema.sql",
            f"{tmp_dir}/001_initial_schema.sql",
        )
        assert self._user_version(legacy_pacs_db) == 0

        before = self._rows(legacy_pacs_db, "stored_instances", "sop_instance_uid")
        assert len(before) == 2

        PACSStorage(str(legacy_pacs_db), str(tmp_dir))

        assert self._user_version(legacy_pacs_db) == 1
        assert self._rows(legacy_pacs_db, "stored_instances", "sop_instance_uid") == before

    def test_pacs_legacy_database_records_are_usable_after_upgrade(self, legacy_pacs_db, tmp_dir):
        """PACS storage: Records in an upgraded legacy database are usable."""
        storage = PACSStorage(str(legacy_pacs_db), str(tmp_dir))

        assert storage.instance_exists(LEGACY_PACS_SOP_INSTANCE_UID) is True

        instance = storage.get_instance(LEGACY_PACS_SOP_INSTANCE_UID)
        assert instance["patient_id"] == "999123456"
        assert instance["patient_name"] == "SMITH^JANE"
        assert instance["accession_number"] == "ACC123456"
        assert instance["status"] == "STORED"

        pending = storage.get_pending_uploads()
        assert [item["sop_instance_uid"] for item in pending] == [LEGACY_PACS_SOP_INSTANCE_UID]

    def test_pacs_legacy_database_can_be_written_to_after_upgrade(self, legacy_pacs_db, tmp_dir):
        """PACS storage: An upgraded legacy database accepts new instances."""
        storage = PACSStorage(str(legacy_pacs_db), str(tmp_dir))

        storage.store_instance(
            NEW_SOP_INSTANCE_UID,
            b"new instance",
            {"patient_id": "999000000", "patient_name": "TEST^PATIENT"},
        )

        assert storage.instance_exists(NEW_SOP_INSTANCE_UID) is True
        assert len(self._rows(legacy_pacs_db, "stored_instances", "sop_instance_uid")) == 3

    def test_worklist_legacy_database_is_upgraded(self, legacy_worklist_db, tmp_dir, monkeypatch):
        """MWL storage: Populated legacy database is upgraded to version 1."""
        monkeypatch.setattr(MWLStorage, "migrations_path", tmp_dir)
        shutil.copy(
            f"{pytest.root_dir}/src/database/worklist/001_initial_schema.sql",
            f"{tmp_dir}/001_initial_schema.sql",
        )
        assert self._user_version(legacy_worklist_db) == 0

        before = self._rows(legacy_worklist_db, "worklist_items", "accession_number")
        assert len(before) == 2

        MWLStorage(str(legacy_worklist_db))

        assert self._user_version(legacy_worklist_db) == 1
        assert self._rows(legacy_worklist_db, "worklist_items", "accession_number") == before

    def test_worklist_legacy_database_records_are_usable_after_upgrade(self, legacy_worklist_db):
        """MWL storage: Records in an upgraded legacy database are usable."""
        storage = MWLStorage(str(legacy_worklist_db))

        item = storage.get_worklist_item("ACC123456")
        assert item is not None
        assert item.patient_id == "999123456"
        assert item.patient_name == "SMITH^JANE"
        assert item.scheduled_date == "20240101"
        assert item.status == "SCHEDULED"
        assert item.source_message_id == "MSGID123456"

        results = storage.find_worklist_items()
        assert len(results) == 2

        by_mpps = storage.get_worklist_item_by_mpps_instance_uid(LEGACY_WORKLIST_MPPS_INSTANCE_UID)
        assert by_mpps is not None
        assert by_mpps.accession_number == "ACC654321"

    def test_worklist_legacy_database_can_be_written_to_after_upgrade(self, legacy_worklist_db):
        """MWL storage: An upgraded legacy database accepts new items."""
        storage = MWLStorage(str(legacy_worklist_db))

        storage.update_status("ACC123456", "IN PROGRESS")

        assert storage.get_worklist_item("ACC123456").status == "IN PROGRESS"
        assert len(self._rows(legacy_worklist_db, "worklist_items", "accession_number")) == 2
