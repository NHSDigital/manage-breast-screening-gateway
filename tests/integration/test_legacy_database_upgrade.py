"""
Integration-style tests for the upgrade of databases created by the legacy
initialisation mechanism.

Databases created by the legacy mechanism hold the schema and their data, but
have a user_version of 0. The migration runner must bring them up to the
current version without re-initialising the schema, so that the existing
records are left untouched.
"""

import sqlite3

import pytest
from pydicom.uid import generate_uid

from services.storage import MWLStorage, PACSStorage

# Schemas as created by the legacy initialisation mechanism, before database
# migrations were introduced. The old Storage._ensure_db() executed these
# scripts directly, and did not set the user_version pragma, so databases
# created before the pragma was introduced hold the schema and their data,
# but with user_version = 0.
LEGACY_PACS_SCHEMA = """
-- PACS Database Schema
-- Stores metadata and file paths for DICOM images

-- Main table for stored DICOM instances
CREATE TABLE IF NOT EXISTS stored_instances (
    -- Primary key: SOP Instance UID
    sop_instance_uid TEXT PRIMARY KEY,

    storage_path TEXT NOT NULL,           -- Relative path from storage root
    file_size INTEGER NOT NULL,           -- File size in bytes
    storage_hash TEXT NOT NULL,           -- Hash for file integrity checks

    patient_id TEXT,
    patient_name TEXT,

    accession_number TEXT,                -- Link to worklist

    status TEXT DEFAULT 'STORED' CHECK(status IN ('STORED', 'ARCHIVED', 'DELETED')),

    upload_status TEXT DEFAULT 'PENDING' CHECK(upload_status IN ('PENDING', 'UPLOADING', 'COMPLETE', 'FAILED')),
    upload_error TEXT,
    upload_attempt_count INTEGER DEFAULT 0,
    last_upload_attempt TEXT,
    uploaded_at TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source_aet TEXT,                      -- AE Title of sender

    UNIQUE(storage_path)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_patient_id ON stored_instances(patient_id);
CREATE INDEX IF NOT EXISTS idx_accession_number ON stored_instances(accession_number);
CREATE INDEX IF NOT EXISTS idx_created_at ON stored_instances(created_at);
CREATE INDEX IF NOT EXISTS idx_storage_hash ON stored_instances(storage_hash);
CREATE INDEX IF NOT EXISTS idx_upload_status ON stored_instances(upload_status);
"""

LEGACY_WORKLIST_SCHEMA = """
-- Modality Worklist SQLite Schema

-- Main worklist items table
CREATE TABLE IF NOT EXISTS worklist_items (
    -- Unique identifier for the scheduled procedure
    accession_number TEXT PRIMARY KEY,

    -- Patient demographics
    patient_id TEXT NOT NULL,
    patient_name TEXT NOT NULL,              -- DICOM format: FAMILY^GIVEN
    patient_birth_date TEXT NOT NULL,        -- YYYYMMDD format
    patient_sex TEXT,                        -- M/F/O

    -- Scheduling information
    scheduled_date TEXT NOT NULL,            -- YYYYMMDD format in UTC
    scheduled_time TEXT NOT NULL,            -- HHMMSS format in UTC
    modality TEXT NOT NULL,                  -- e.g., MG for mammography

    -- Procedure details
    study_description TEXT,
    procedure_code TEXT,

    -- Status tracking
    status TEXT DEFAULT 'SCHEDULED' CHECK(status IN ('SCHEDULED', 'IN PROGRESS', 'COMPLETED', 'DISCONTINUED')),

    -- DICOM identifiers
    study_instance_uid TEXT,
    mpps_instance_uid TEXT, -- Modality Performed Procedure Step (MPPS) UID

    -- Audit trail
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    -- Link to source message from relay listener
    source_message_id TEXT
);

-- Index for the most common query pattern (MWL C-FIND by modality and date)
CREATE INDEX IF NOT EXISTS idx_worklist_date_modality
ON worklist_items(scheduled_date, modality);

-- Index for status queries (finding in-progress procedures, etc.)
CREATE INDEX IF NOT EXISTS idx_worklist_status
ON worklist_items(status);

-- Index for MPPS lookups by study instance UID
CREATE INDEX IF NOT EXISTS idx_worklist_study_uid
ON worklist_items(study_instance_uid);

-- Index for patient lookups
CREATE INDEX IF NOT EXISTS idx_worklist_patient_id
ON worklist_items(patient_id);

-- Index for MPPS instance UID lookups
CREATE INDEX IF NOT EXISTS idx_worklist_mpps_instance_uid
ON worklist_items(mpps_instance_uid);
"""

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

    def test_pacs_legacy_database_is_upgraded(self, legacy_pacs_db, tmp_dir):
        """PACS storage: Populated legacy database is upgraded to version 1."""
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

    def test_worklist_legacy_database_is_upgraded(self, legacy_worklist_db):
        """MWL storage: Populated legacy database is upgraded to version 1."""
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
