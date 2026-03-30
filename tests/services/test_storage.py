import hashlib
import sqlite3
from pathlib import Path

import pytest
from pydicom.uid import generate_uid

from models import WorklistItem
from services.storage import InvalidStatusTransitionError, MWLStorage, PACSStorage, WorklistItemNotFoundError


@pytest.fixture
def db_file(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def pacs_storage(db_file, tmp_path):
    storage = PACSStorage(str(db_file), str(tmp_path))
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
    }


class TestPACSStorage:
    def test_init(self, pacs_storage, db_file):
        assert Path(db_file).exists()

        conn = sqlite3.connect(db_file)
        table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stored_instances'").fetchone()

        assert table is not None

    def test_instance_exists_returns_true(self, pacs_storage):
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
        assert pacs_storage.instance_exists("1.2.3") is False

    def test_store_instance_saves_to_filesystem(self, pacs_storage):
        uid = generate_uid()
        metadata = {"patient_id": "9990001112", "patient_name": "SMITH^JANE"}

        filepath = pacs_storage.store_instance(uid, b"foo", metadata)

        assert Path(filepath).exists()
        assert Path(filepath).read_bytes() == b"foo"

        hex_hash = hashlib.sha256(uid.encode()).hexdigest()
        expected_rel = f"{hex_hash[:2]}/{hex_hash[2:4]}/{hex_hash[:16]}.dcm"

        assert expected_rel in filepath

    def test_store_instance_saves_to_db(self, pacs_storage):
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


class TestWorkingStorage:
    def _insert_item(self, storage, result):
        item = WorklistItem(**result)
        storage.store_worklist_item(item)
        return item

    def test_init(self, mwl_storage, db_file):
        conn = sqlite3.connect(db_file)
        table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='worklist_items'").fetchone()

        assert table is not None

    def test_store_worklist_item(self, mwl_storage, result):
        item = WorklistItem(**result)

        mwl_storage.store_worklist_item(item)

        with mwl_storage._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM worklist_items WHERE accession_number = ?",
                (item.accession_number,),
            ).fetchone()

        assert row is not None
        assert row["patient_id"] == item.patient_id

    def test_find_worklist_items(self, mwl_storage, result):
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
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(**{query_param_name: query_param_value})

        assert len(results) == 1

    def test_find_worklist_items_with_multiple_filters(self, mwl_storage, result):
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(
            accession_number="ACC123456",
            modality="MG",
            scheduled_date="20240101",
            patient_id="999123456",
        )

        assert len(results) == 1

    def test_find_worklist_items_with_date_range(self, mwl_storage, result):
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(scheduled_date="20240101 - 20240131")

        assert len(results) == 1

    def test_find_worklist_items_with_open_ended_date_range(self, mwl_storage, result):
        self._insert_item(mwl_storage, result)

        assert len(mwl_storage.find_worklist_items(scheduled_date="20240101 -")) == 1
        assert len(mwl_storage.find_worklist_items(scheduled_date="-20240101")) == 1

    def test_find_worklist_items_with_time_range(self, mwl_storage, result):
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(scheduled_time="090000 - 170000")

        assert len(results) == 1

    def test_find_worklist_items_with_open_ended_time_range(self, mwl_storage, result):
        self._insert_item(mwl_storage, result)

        assert len(mwl_storage.find_worklist_items(scheduled_time="090000 -")) == 1

    def test_find_worklist_items_with_date_and_time_range(self, mwl_storage, result):
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(
            scheduled_date="20240101 - 20240131",
            scheduled_time="090000 - 170000",
        )

        assert len(results) == 1

    @pytest.mark.parametrize("wildcard_param", ["Smith*", "*Smith*", "Sm?th*", "Smith^Jane"])
    def test_find_worklist_items_patient_name_wildcard_conversion(self, mwl_storage, result, wildcard_param):
        self._insert_item(mwl_storage, result)

        results = mwl_storage.find_worklist_items(patient_name=wildcard_param)

        assert len(results) == 1
        assert results[0].patient_name == "SMITH^JANE"

    def test_get_worklist_item(self, mwl_storage, result):
        item = self._insert_item(mwl_storage, result)

        fetched = mwl_storage.get_worklist_item(item.accession_number)

        assert fetched == item

    def test_get_worklist_item_returns_none(self, mwl_storage):
        assert mwl_storage.get_worklist_item("DOES_NOT_EXIST") is None

    def test_update_status(self, mwl_storage, result):
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        returned = mwl_storage.update_status(item.accession_number, "COMPLETED")

        assert returned == item.source_message_id
        assert mwl_storage.get_worklist_item(item.accession_number).status == "COMPLETED"

    def test_update_status_returns_none_when_not_found(self, mwl_storage):
        assert mwl_storage.update_status("DOES_NOT_EXIST", "IN PROGRESS") is None

    def test_update_status_with_mpps(self, mwl_storage, result):
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
        item = self._insert_item(mwl_storage, result)

        with pytest.raises(InvalidStatusTransitionError):
            mwl_storage.update_status(item.accession_number, "SCHEDULED")  # SCHEDULED is never a valid target

    def test_update_status_returns_none_on_wrong_state(self, mwl_storage, result):
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        assert mwl_storage.update_status(item.accession_number, "IN PROGRESS") is None

    def test_update_study_instance_uid(self, mwl_storage, result):
        item = self._insert_item(mwl_storage, result)

        assert mwl_storage.update_study_instance_uid(item.accession_number, "new-uid") is True

    def test_update_study_instance_uid_raises(self, mwl_storage):
        with pytest.raises(WorklistItemNotFoundError):
            mwl_storage.update_study_instance_uid("DOES_NOT_EXIST", "uid")

    def test_delete_worklist_item(self, mwl_storage, result):
        item = self._insert_item(mwl_storage, result)

        assert mwl_storage.delete_worklist_item(item.accession_number) is True

        with mwl_storage._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM worklist_items WHERE accession_number = ?",
                (item.accession_number,),
            ).fetchone()

        assert row is None

    def test_delete_worklist_item_raises(self, mwl_storage):
        with pytest.raises(WorklistItemNotFoundError):
            mwl_storage.delete_worklist_item("DOES_NOT_EXIST")

    def test_mpps_instance_exists(self, mwl_storage, result):
        uid = generate_uid()
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        mwl_storage.update_status(item.accession_number, "COMPLETED", mpps_instance_uid=uid)

        assert mwl_storage.mpps_instance_exists(uid) is True

    def test_mpps_instance_not_exists(self, mwl_storage):
        assert mwl_storage.mpps_instance_exists("nope") is False

    def test_get_worklist_item_by_mpps_instance_uid(self, mwl_storage, result):
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
        assert mwl_storage.get_worklist_item_by_mpps_instance_uid("nope") is None

    def test_update_status_scheduled_to_in_progress(self, mwl_storage, result):
        item = self._insert_item(mwl_storage, result)

        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        assert mwl_storage.get_worklist_item(item.accession_number).status == "IN PROGRESS"

    def test_update_status_in_progress_to_discontinued(self, mwl_storage, result):
        item = self._insert_item(mwl_storage, result)
        mwl_storage.update_status(item.accession_number, "IN PROGRESS")

        mwl_storage.update_status(item.accession_number, "DISCONTINUED")

        assert mwl_storage.get_worklist_item(item.accession_number).status == "DISCONTINUED"
