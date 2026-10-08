import hashlib
import multiprocessing
import shutil
import sqlite3
from pathlib import Path

import pytest
from pydicom.uid import generate_uid

from models import WorklistItem
from services.mwl import InvalidStatusTransitionError
from services.storage import (
    MWLStorage,
    PACSStorage,
    Storage,
    WorklistItemExistsError,
    WorklistItemNotFoundError,
)


@pytest.fixture
def db_file(tmp_dir):
    return tmp_dir / "test.db"


@pytest.fixture
def pacs_storage(db_file, tmp_dir):
    storage = PACSStorage(str(db_file), str(tmp_dir))
    return storage


@pytest.fixture
def mwl_storage(db_file):
    storage = MWLStorage(str(db_file))
    return storage


@pytest.fixture
def result():
    return {
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
        "study_instance_uid": generate_uid(),
        "source_message_id": "MSGID123456",
        "source_system_url": "https://example.com",
    }


class TestPACSStorage:
    def test_init(self, pacs_storage, db_file):
        """PACS storage: Init."""
        assert Path(db_file).exists()

        conn = sqlite3.connect(db_file)
        table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stored_instances'").fetchone()
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.close()

        assert table is not None
        assert user_version == 1

    def test_migrations_path(self, pacs_storage):
        """PACS storage: Migrations path."""
        assert "database/pacs" in pacs_storage.migrations_path

    def test_migrate_db(self, db_file, tmp_dir, monkeypatch):
        """PACS storage migrate db."""
        monkeypatch.setattr(PACSStorage, "migrations_path", tmp_dir)

        shutil.copy(
            f"{Path(__file__).parent.parent.parent}/src/database/pacs/001_initial_schema.sql",
            tmp_dir / "001_initial_schema.sql",
        )

        for i in range(2, 5):
            with open(tmp_dir / f"00{i}_add_new_column_{i}.sql", "w") as f:
                f.write(
                    f"""
                    ALTER TABLE stored_instances ADD COLUMN new_column_{i} TEXT;
                    """
                )

        storage = PACSStorage(str(db_file), str(tmp_dir))

        with storage._get_connection() as conn:
            user_version = conn.execute("PRAGMA user_version").fetchone()[0]
            table_info = conn.execute("PRAGMA table_info(stored_instances)").fetchall()

        assert user_version == 4
        assert any(column[1] == "new_column_4" for column in table_info)

    def test_migrate_db_no_migrations(self, db_file, tmp_dir, monkeypatch):
        """PACS storage migrate db no migrations."""
        monkeypatch.setattr(PACSStorage, "migrations_path", tmp_dir)

        storage = PACSStorage(str(db_file), str(tmp_dir))

        with storage._get_connection() as conn:
            user_version = conn.execute("PRAGMA user_version").fetchone()[0]

        assert user_version == 0

    def test_instance_exists_returns_true(self, pacs_storage):
        """Instance exists returns true."""
        uid = generate_uid()

        with pacs_storage._get_connection() as conn:
            conn.execute(
                (
                    "INSERT INTO stored_instances (sop_instance_uid, storage_path, file_size, storage_hash, status) "
                    "VALUES (?, ?, ?, ?, 'STORED')"
                ),
                (uid, "/path/to/file.dcm", 12345, "abcdef1234567890"),
            )
            conn.commit()

        assert pacs_storage.instance_exists(uid) is True

    def test_instance_exists_returns_false(self, pacs_storage):
        """Instance exists returns false."""
        assert pacs_storage.instance_exists("1.2.3") is False

    def test_store_instance_saves_to_filesystem(self, pacs_storage):
        """Store instance saves to filesystem."""
        uid = generate_uid()
        metadata = {"patient_id": "9990001112", "patient_name": "SMITH^JANE"}

        filepath = pacs_storage.store_instance(uid, b"foo", metadata)

        assert Path(filepath).exists()
        assert Path(filepath).read_bytes() == b"foo"

        hex_hash = hashlib.sha256(uid.encode()).hexdigest()
        expected_rel = f"{hex_hash[:2]}/{hex_hash[2:4]}/{hex_hash[:16]}.dcm"

        assert expected_rel in filepath

    def test_store_instance_saves_to_db(self, pacs_storage):
        """Store instance saves to db."""
        uid = generate_uid()

        metadata = {
            "accession_number": "ACC112233",
            "patient_id": "9990001112",
            "patient_name": "SMITH^JANE",
        }

        pacs_storage.store_instance(uid, b"foo", metadata)

        with pacs_storage._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM stored_instances WHERE sop_instance_uid = ?",
                (uid,),
            ).fetchone()

        assert row is not None
        assert row["status"] == "STORED"
        assert row["patient_id"] == metadata["patient_id"]
        assert row["patient_name"] == metadata["patient_name"]
        assert row["accession_number"] == metadata["accession_number"]


class TestMWLStorage:
    def _insert_item(self, storage, result):
        item = WorklistItem(**result)
        storage.store_worklist_item(item)
        return item

    def test_init(self, mwl_storage, db_file):
        """MWL storage: Init."""
        conn = sqlite3.connect(db_file)
        table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='worklist_items'").fetchone()
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.close()

        assert table is not None
        assert user_version == 1

    def test_migrations_path(self, mwl_storage):
        """MWL storage: Migrations path."""
        assert "database/worklist" in mwl_storage.migrations_path

    def test_migrate_db(self, db_file, tmp_dir, monkeypatch):
        """MWL storage migrate db."""
        monkeypatch.setattr(MWLStorage, "migrations_path", tmp_dir)

        shutil.copy(
            f"{Path(__file__).parent.parent.parent}/src/database/worklist/001_initial_schema.sql",
            tmp_dir / "001_initial_schema.sql",
        )

        for i in range(2, 4):
            with open(tmp_dir / f"00{i}_add_new_column_{i}.sql", "w") as f:
                f.write(
                    f"""
                    ALTER TABLE worklist_items ADD COLUMN new_column_{i} TEXT;
                    """
                )

        storage = MWLStorage(str(db_file))

        with storage._get_connection() as conn:
            user_version = conn.execute("PRAGMA user_version").fetchone()[0]
            table_info = conn.execute("PRAGMA table_info(worklist_items)").fetchall()

        assert user_version == 3
        assert any(column[1] == "new_column_3" for column in table_info)

    def test_store_worklist_item(self, mwl_storage, result):
        """Store worklist item."""
        item = WorklistItem(**result)

        mwl_storage.store_worklist_item(item)

        with mwl_storage._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM worklist_items WHERE accession_number = ?",
                (item.accession_number,),
            ).fetchone()

        assert row is not None
        assert row["patient_id"] == item.patient_id

    def test_store_worklist_item_already_exists(self, mwl_storage, result):
        """Store worklist item already exists."""
        item = WorklistItem(**result)
        mwl_storage.store_worklist_item(item)

        with pytest.raises(WorklistItemExistsError):
            mwl_storage.store_worklist_item(item)

    def test_find_worklist_items(self, mwl_storage, result):
        """Find worklist items."""
        item = self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items()

        assert len(results) == 1
        assert results[0] == item

    @pytest.mark.parametrize(
        "query_param_name, query_param_value",
        [
            ("accession_number", "ACC123456"),
            ("patient_id", "999123456"),
            ("modality", "MG"),
            ("scheduled_date", "20240101"),
        ],
    )
    def test_find_worklist_items_with_filters(self, mwl_storage, result, query_param_name, query_param_value):
        """Find worklist items with filters."""
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(**{query_param_name: query_param_value})

        assert len(results) == 1

    def test_find_worklist_items_with_multiple_filters(self, mwl_storage, result):
        """Find worklist items with multiple filters."""
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(
            accession_number="ACC123456",
            modality="MG",
            scheduled_date="20240101",
            patient_id="999123456",
        )

        assert len(results) == 1

    def test_find_worklist_items_with_date_range(self, mwl_storage, result):
        """Find worklist items with date range."""
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(scheduled_date="20240101 - 20240131")

        assert len(results) == 1

    def test_find_worklist_items_with_open_ended_date_range(self, mwl_storage, result):
        """Find worklist items with open ended date range."""
        self._insert_item(mwl_storage, result)

        assert len(mwl_storage.find_worklist_items(scheduled_date="20240101 -")) == 1
        assert len(mwl_storage.find_worklist_items(scheduled_date="-20240101")) == 1

    def test_find_worklist_items_with_time_range(self, mwl_storage, result):
        """Find worklist items with time range."""
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(scheduled_time="090000 - 170000")

        assert len(results) == 1

    def test_find_worklist_items_with_open_ended_time_range(self, mwl_storage, result):
        """Find worklist items with open ended time range."""
        self._insert_item(mwl_storage, result)

        assert len(mwl_storage.find_worklist_items(scheduled_time="090000 -")) == 1

    def test_find_worklist_items_with_date_and_time_range(self, mwl_storage, result):
        """Find worklist items with date and time range."""
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(
            scheduled_date="20240101 - 20240131",
            scheduled_time="090000 - 170000",
        )

        assert len(results) == 1

    @pytest.mark.parametrize("wildcard_param", ["Smith*", "*Smith*", "Sm?th*", "Smith^Jane"])
    def test_find_worklist_items_patient_name_wildcard_conversion(self, mwl_storage, result, wildcard_param):
        """Find worklist items patient name wildcard conversion."""
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(patient_name=wildcard_param)

        assert len(results) == 1
        assert results[0].patient_name == "SMITH^JANE"

    def test_find_worklist_items_with_filters_completed_items(self, mwl_storage, result):
        """Find worklist items with filters completed items."""
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")
        mwl_storage.update_status(item.accession_number, "COMPLETED")

        results = mwl_storage.find_worklist_items(
            accession_number="ACC123456",
            modality="MG",
            scheduled_date="20240101",
            patient_id="999123456",
        )

        assert len(results) == 0

    def test_find_worklist_items_with_filters_discontinued_items(self, mwl_storage, result):
        """Find worklist items with filters discontinued items."""
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")
        mwl_storage.update_status(item.accession_number, "DISCONTINUED")

        results = mwl_storage.find_worklist_items(
            accession_number="ACC123456",
            modality="MG",
            scheduled_date="20240101",
            patient_id="999123456",
        )

        assert len(results) == 0

    def test_get_worklist_item(self, mwl_storage, result):
        """Get worklist item."""
        item = self._insert_item(mwl_storage, result)

        fetched = mwl_storage.get_worklist_item(item.accession_number)

        assert fetched == item

    def test_get_worklist_item_returns_none(self, mwl_storage):
        """Get worklist item returns none."""
        assert mwl_storage.get_worklist_item("DOES_NOT_EXIST") is None

    def test_update_status(self, mwl_storage, result):
        """MWL storage: Update status."""
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        returned = mwl_storage.update_status(item.accession_number, "COMPLETED")

        assert returned == item.source_message_id
        assert mwl_storage.get_worklist_item(item.accession_number).status == "COMPLETED"

    def test_update_status_returns_none_when_not_found(self, mwl_storage):
        """MWL storage: Update status returns none when not found."""
        assert mwl_storage.update_status("DOES_NOT_EXIST", "IN PROGRESS") is None

    def test_update_status_with_mpps(self, mwl_storage, result):
        """MWL storage: Update status with MPPS."""
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        returned = mwl_storage.update_status(
            item.accession_number,
            "COMPLETED",
            mpps_instance_uid="some-uid",
        )

        assert returned == item.source_message_id
        assert mwl_storage.get_worklist_item(item.accession_number).mpps_instance_uid == "some-uid"

    def test_update_status_raises_on_invalid_target(self, mwl_storage, result):
        """MWL storage: Update status raises on invalid target."""
        item = self._insert_item(mwl_storage, result)

        with pytest.raises(InvalidStatusTransitionError):
            mwl_storage.update_status(item.accession_number, "SCHEDULED")  # SCHEDULED is never a valid target

    def test_update_status_returns_none_on_wrong_state(self, mwl_storage, result):
        """MWL storage: Update status returns none on wrong state."""
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        assert mwl_storage.update_status(item.accession_number, "IN PROGRESS") is None

    def test_update_study_instance_uid(self, mwl_storage, result):
        """MWL storage: Update study instance UID."""
        item = self._insert_item(mwl_storage, result)

        assert mwl_storage.update_study_instance_uid(item.accession_number, "new-uid") is True

    def test_update_study_instance_uid_raises(self, mwl_storage):
        """MWL storage: Update study instance UID raises."""
        with pytest.raises(WorklistItemNotFoundError):
            mwl_storage.update_study_instance_uid("DOES_NOT_EXIST", "uid")

    def test_delete_worklist_item(self, mwl_storage, result):
        """Delete worklist item."""
        item = self._insert_item(mwl_storage, result)

        assert mwl_storage.delete_worklist_item(item.accession_number) is True

        with mwl_storage._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM worklist_items WHERE accession_number = ?",
                (item.accession_number,),
            ).fetchone()

        assert row is None

    def test_delete_worklist_item_raises(self, mwl_storage):
        """Delete worklist item raises."""
        with pytest.raises(WorklistItemNotFoundError):
            mwl_storage.delete_worklist_item("DOES_NOT_EXIST")

    def test_mpps_instance_exists(self, mwl_storage, result):
        """MPPS instance exists."""
        uid = generate_uid()
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        mwl_storage.update_status(item.accession_number, "COMPLETED", mpps_instance_uid=uid)

        assert mwl_storage.mpps_instance_exists(uid) is True

    def test_mpps_instance_not_exists(self, mwl_storage):
        """MPPS instance not exists."""
        assert mwl_storage.mpps_instance_exists("nope") is False

    def test_get_worklist_item_by_mpps_instance_uid(self, mwl_storage, result):
        """Get worklist item by MPPS instance UID."""
        uid = generate_uid()
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        mwl_storage.update_status(item.accession_number, "COMPLETED", mpps_instance_uid=uid)

        fetched = mwl_storage.get_worklist_item_by_mpps_instance_uid(uid)

        assert fetched.accession_number == item.accession_number
        assert fetched.mpps_instance_uid == uid
        assert fetched.status == "COMPLETED"
        assert fetched.source_message_id == item.source_message_id
        assert fetched.patient_id == item.patient_id

    def test_get_worklist_item_by_mpps_instance_uid_returns_none(self, mwl_storage):
        """Get worklist item by MPPS instance UID returns none."""
        assert mwl_storage.get_worklist_item_by_mpps_instance_uid("nope") is None

    def test_update_status_scheduled_to_in_progress(self, mwl_storage, result):
        """MWL storage: Update status scheduled to in progress."""
        item = self._insert_item(mwl_storage, result)

        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        assert mwl_storage.get_worklist_item(item.accession_number).status == "IN PROGRESS"

    def test_update_status_scheduled_to_discontinued(self, mwl_storage, result):
        """MWL storage: Update status scheduled to discontinued."""
        item = self._insert_item(mwl_storage, result)
        assert item.status == "SCHEDULED"

        mwl_storage.update_status(item.accession_number, "DISCONTINUED")

        assert mwl_storage.get_worklist_item(item.accession_number).status == "DISCONTINUED"

    def test_update_status_in_progress_to_completed(self, mwl_storage, result):
        """MWL storage: Update status in progress to completed."""
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        mwl_storage.update_status(item.accession_number, "COMPLETED")

        assert mwl_storage.get_worklist_item(item.accession_number).status == "COMPLETED"

    def test_update_status_in_progress_to_discontinued(self, mwl_storage, result):
        """MWL storage: Update status in progress to discontinued."""
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        mwl_storage.update_status(item.accession_number, "DISCONTINUED")

        assert mwl_storage.get_worklist_item(item.accession_number).status == "DISCONTINUED"

    @pytest.mark.parametrize(
        "source_message_id, source_system_url",
        [
            ("MSGID123456", "https://example.com"),
            (None, "https://example.com"),
            ("MSGID123456", None),
            (None, None),
        ],
    )
    def test_get_source_attributes(self, mwl_storage, result, source_message_id, source_system_url):
        """Get source attributes."""
        result["source_message_id"] = source_message_id
        result["source_system_url"] = source_system_url

        item = self._insert_item(mwl_storage, result)

        source_attrs = mwl_storage.get_source_attributes(item.accession_number)

        assert source_attrs == (item.source_message_id, item.source_system_url)

    def test_get_source_attributes_returns_none_when_not_found(self, mwl_storage):
        """Get source attributes returns none when not found."""
        assert mwl_storage.get_source_attributes("DOES_NOT_EXIST") == (None, None)

    def test_get_source_message_id(self, mwl_storage, result):
        """Get source message id."""
        item = self._insert_item(mwl_storage, result)

        source_message_id = mwl_storage.get_source_message_id(item.accession_number)

        assert source_message_id == item.source_message_id

    def test_get_source_message_id_returns_none_when_not_found(self, mwl_storage):
        """Get source message id returns none when not found."""
        assert mwl_storage.get_source_message_id("DOES_NOT_EXIST") is None



class TestStorageMigrationLock:
    def _worker(self, db_path, migrations_dir, barrier):
        class TestStorage(Storage):
            @property
            def migrations_path(self):
                return str(migrations_dir)

        barrier.wait(timeout=10)
        TestStorage(db_path=str(db_path))

    def test_migration_lock_prevents_concurrent_processes(self, tmp_dir):
        db_path = tmp_dir / "test.db"
        migrations_dir = tmp_dir / "migrations"
        migrations_dir.mkdir()

        (migrations_dir / "001_init.sql").write_text(
            """
            CREATE TABLE items (id INTEGER PRIMARY KEY);
            INSERT INTO items DEFAULT VALUES;
            """
        )

        ctx = multiprocessing.get_context("spawn")
        barrier = ctx.Barrier(2)
        procs = [ctx.Process(target=self._worker, args=(db_path, migrations_dir, barrier)) for _ in range(2)]

        for p in procs:
            p.start()

        for p in procs:
            p.join()

        assert all(p.exitcode == 0 for p in procs)

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.close()

        assert rows == 1
        assert version == 1


class TestStoragePartialMigration:
    def _make_storage(self, db_path, migrations_dir):
        class TestStorage(Storage):
            @property
            def migrations_path(self):
                return str(migrations_dir)

        return TestStorage(db_path=str(db_path))

    def test_applies_only_pending_migrations(self, tmp_dir):
        """Storage: Only migrations newer than user_version are applied."""
        db_path = tmp_dir / "test.db"
        migrations_dir = tmp_dir / "migrations"
        migrations_dir.mkdir()

        (migrations_dir / "001_init.sql").write_text(
            "CREATE TABLE items (id INTEGER PRIMARY KEY);INSERT INTO items DEFAULT VALUES;"
        )

        # First run: only migration 001 exists
        self._make_storage(db_path, migrations_dir)

        # New migrations are added later. 001 is not idempotent, so
        # re-running it would fail with "table items already exists".
        (migrations_dir / "002_add_name.sql").write_text("ALTER TABLE items ADD COLUMN name TEXT;")
        (migrations_dir / "003_add_flag.sql").write_text("ALTER TABLE items ADD COLUMN flag INTEGER DEFAULT 0;")

        # Second run: database is at version 1, should apply 002 and 003 only
        self._make_storage(db_path, migrations_dir)

        conn = sqlite3.connect(db_path)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        columns = [c[1] for c in conn.execute("PRAGMA table_info(items)")]
        rows = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        conn.close()

        assert version == 3
        assert "name" in columns
        assert "flag" in columns
        assert rows == 1  # data from migration 001 not duplicated

    def test_no_op_when_fully_migrated(self, tmp_dir):
        """Storage: Re-initialising a fully migrated database changes nothing."""
        db_path = tmp_dir / "test.db"
        migrations_dir = tmp_dir / "migrations"
        migrations_dir.mkdir()

        (migrations_dir / "001_init.sql").write_text(
            "CREATE TABLE items (id INTEGER PRIMARY KEY);INSERT INTO items DEFAULT VALUES;"
        )

        self._make_storage(db_path, migrations_dir)
        self._make_storage(db_path, migrations_dir)

        conn = sqlite3.connect(db_path)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        rows = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        conn.close()

        assert version == 1
        assert rows == 1

    def test_partial_migration_with_existing_data(self, tmp_dir):
        """Storage: Partial migration with existing data."""
        db_path = tmp_dir / "test.db"
        migrations_dir = tmp_dir / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_init.sql").write_text(
            "CREATE TABLE items (id INTEGER PRIMARY KEY);INSERT INTO items DEFAULT VALUES;"
        )
        (migrations_dir / "002_add_name.sql").write_text("ALTER TABLE items ADD COLUMN name TEXT;")
        (migrations_dir / "003_add_flag.sql").write_text("ALTER TABLE items ADD COLUMN flag INTEGER DEFAULT 0;")
        # First run: apply all migrations
        self._make_storage(db_path, migrations_dir)
        # Insert some data
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO items (name, flag) VALUES (?, ?)", ("test", 1))
        conn.commit()
        conn.close()
        # Add a new migration
        (migrations_dir / "004_add_description.sql").write_text("ALTER TABLE items ADD COLUMN description TEXT;")
        # Second run: should apply only the new migration
        self._make_storage(db_path, migrations_dir)
        conn = sqlite3.connect(db_path)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        columns = [c[1] for c in conn.execute("PRAGMA table_info(items)")]
        rows = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        conn.close()
        assert version == 4
        assert "description" in columns
        assert rows == 2  # existing data preserved

    def test_migration_rollback_on_error(self, tmp_dir):
        """Storage: Migration rollback on error."""
        db_path = tmp_dir / "test.db"
        migrations_dir = tmp_dir / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_init.sql").write_text(
            "CREATE TABLE items (id INTEGER PRIMARY KEY);INSERT INTO items DEFAULT VALUES;"
        )
        # First run: apply migration 001
        self._make_storage(db_path, migrations_dir)
        # Second run: migration 002 should fail and rollback
        (migrations_dir / "002_invalid.sql").write_text(
            "ALTER TABLE items ADD COLUMN name TEXT;"
            "INSERT INTO items DEFAULT VALUES;"
            "ALTER TABLE non_existing_table ADD COLUMN name TEXT;"
        )
        with pytest.raises(sqlite3.OperationalError):
            self._make_storage(db_path, migrations_dir)
        conn = sqlite3.connect(db_path)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        rows = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        columns = [column[1] for column in conn.execute("PRAGMA table_info(items)")]
        conn.close()
        assert version == 1  # version should not have changed
        assert rows == 1  # data from migration 001 should still exist
        assert "name" not in columns  # schema changes should also be rolled back
