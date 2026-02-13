import hashlib
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from pydicom.uid import generate_uid

from services.storage import MWLStorage, PACSStorage, WorklistItem, WorklistItemNotFoundError


@patch("services.storage.sqlite3")
class TestPACSStorage:
    def test_init(self, mock_db, tmp_dir):
        mock_connection = MagicMock()
        mock_db.connect.return_value = mock_connection
        subject = PACSStorage(tmp_dir, tmp_dir)

        assert subject.db_path == tmp_dir
        assert subject.storage_root == Path(tmp_dir)
        assert subject.storage_root.exists()
        assert subject.schema_path == f"{Path(__file__).parent.parent.parent}/src/services/init_pacs_db.sql"
        assert subject.table_name == "stored_instances"

        assert mock_connection.execute.call_count == 3
        mock_connection.execute.assert_any_call("PRAGMA journal_mode=WAL")
        mock_connection.execute.assert_any_call("PRAGMA synchronous=NORMAL")
        mock_connection.commit.assert_called_once()

    def test_instance_exists_returns_true(self, mock_db, tmp_dir):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection
        subject = PACSStorage(tmp_dir, tmp_dir)
        mock_connection.reset_mock()

        assert subject.instance_exists("1.2.3.4.5.6") is True  # gitleaks:allow

        mock_connection.execute.assert_called_once_with(
            "SELECT 1 FROM stored_instances WHERE sop_instance_uid = ? AND status = 'STORED'",
            ("1.2.3.4.5.6",),  # gitleaks:allow
        )

    def test_instance_exists_returns_false(self, mock_db, tmp_dir):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection
        subject = PACSStorage(tmp_dir, tmp_dir)
        mock_connection.reset_mock()

        assert subject.instance_exists("1.2.3.4.5.6") is False  # gitleaks:allow

    def test_store_instance_saves_to_filesystem(self, mock_db, tmp_dir):
        sop_instance_uid = "1.2.3.4.5.6"  # gitleaks:allow
        mock_connection = MagicMock()
        mock_db.connect.return_value = mock_connection
        subject = PACSStorage(tmp_dir, tmp_dir)
        subject.instance_exists = MagicMock(return_value=False)
        metadata = {"patient_id": "9990001112", "patient_name": "SMITH^JANE"}

        filepath = subject.store_instance(
            sop_instance_uid,
            b"foo",
            metadata,
        )

        hex = hashlib.sha256(sop_instance_uid.encode()).hexdigest()
        relative_path = f"{hex[:2]}/{hex[2:4]}/{hex[:16]}.dcm"

        assert subject._compute_storage_path(sop_instance_uid) == relative_path
        assert relative_path in filepath
        assert open(filepath).read() == "foo"

    def test_store_instance_saves_to_db(self, mock_db, tmp_dir):
        mock_connection = MagicMock()
        mock_db.connect.return_value = mock_connection
        subject = PACSStorage(tmp_dir, tmp_dir)
        subject.instance_exists = MagicMock(return_value=False)
        mock_connection.reset_mock()

        metadata = {
            "accession_number": "ACC112233",
            "patient_id": "9990001112",
            "patient_name": "SMITH^JANE",
        }

        subject.store_instance(
            "1.2.3.4.5.6",  # gitleaks:allow
            b"foo",
            metadata,
        )

        mock_connection.execute.assert_called_once_with(
            """
                INSERT INTO stored_instances (
                    sop_instance_uid, storage_path, file_size, storage_hash,
                    patient_id, patient_name, accession_number, source_aet,
                    status
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    'STORED'
                )
            """,
            (
                "1.2.3.4.5.6",  # gitleaks:allow
                "ff/af/ffaff041ab509297.dcm",
                3,
                "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
                metadata.get("patient_id"),
                metadata.get("patient_name"),
                metadata.get("accession_number"),
                "UNKNOWN",
            ),
        )
        mock_connection.commit.assert_called_once()


@patch("services.storage.sqlite3")
class TestWorkingStorage:
    @pytest.fixture
    def result(self):
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

    def test_init(self, mock_db, tmp_dir):
        mock_connection = MagicMock()
        mock_db.connect.return_value = mock_connection
        subject = MWLStorage(tmp_dir)

        assert subject.db_path == tmp_dir
        assert subject.schema_path == f"{Path(__file__).parent.parent.parent}/src/services/init_worklist_db.sql"
        assert subject.table_name == "worklist_items"

        assert mock_connection.execute.call_count == 3
        mock_connection.execute.assert_any_call("PRAGMA journal_mode=WAL")
        mock_connection.execute.assert_any_call("PRAGMA synchronous=NORMAL")
        mock_connection.commit.assert_called_once()

        assert mock_connection.execute.call_count == 3
        mock_connection.execute.assert_any_call("PRAGMA journal_mode=WAL")
        mock_connection.execute.assert_any_call("PRAGMA synchronous=NORMAL")
        mock_connection.commit.assert_called_once()

    def test_store_worklist_item(self, mock_db, tmp_dir):
        mock_connection = MagicMock()
        mock_db.connect.return_value = mock_connection
        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        item = WorklistItem(
            accession_number="ACC123456",
            patient_id="999123456",
            patient_name="SMITH^JANE",
            patient_birth_date="19800101",
            patient_sex="F",
            scheduled_date="20240101",
            scheduled_time="090000",
            modality="MG",
            study_description="MAMMOGRAPHY",
            procedure_code="12345-6",
            study_instance_uid=generate_uid(),
            source_message_id="MSGID123456",
        )

        subject.store_worklist_item(item)

        mock_connection.execute.assert_called_once_with(
            (
                "INSERT INTO worklist_items (accession_number, modality, patient_birth_date, "
                "patient_id, patient_name, patient_sex, procedure_code, scheduled_date, "
                "scheduled_time, source_message_id, study_description, study_instance_uid) "
                "VALUES (:accession_number, :modality, :patient_birth_date, "
                ":patient_id, :patient_name, :patient_sex, :procedure_code, "
                ":scheduled_date, :scheduled_time, :source_message_id, "
                ":study_description, :study_instance_uid)"
            ),
            item.__dict__,
        )
        mock_connection.commit.assert_called_once()

    def test_find_worklist_items(self, mock_db, tmp_dir, result):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [result]
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection
        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        results = subject.find_worklist_items()

        mock_connection.execute.assert_called_once_with(
            (
                "SELECT accession_number, modality, patient_birth_date, patient_id, "
                "patient_name, patient_sex, procedure_code, scheduled_date, scheduled_time, "
                "source_message_id, study_description, study_instance_uid, status, mpps_instance_uid "
                "FROM worklist_items ORDER BY scheduled_date, scheduled_time"
            ),
            [],
        )

        assert len(results) == 1
        assert results[0] == WorklistItem(**result)

    def test_find_worklist_items_with_filters(self, mock_db, tmp_dir):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        subject.find_worklist_items(patient_id="999123456")

        mock_connection.execute.assert_called_once_with(
            (
                "SELECT accession_number, modality, patient_birth_date, patient_id, "
                "patient_name, patient_sex, procedure_code, scheduled_date, scheduled_time, "
                "source_message_id, study_description, study_instance_uid, status, mpps_instance_uid "
                "FROM worklist_items WHERE patient_id = ? ORDER BY scheduled_date, scheduled_time"
            ),
            ["999123456"],
        )

        mock_connection.reset_mock()
        subject.find_worklist_items(modality="CT")

        mock_connection.execute.assert_called_once_with(
            (
                "SELECT accession_number, modality, patient_birth_date, patient_id, "
                "patient_name, patient_sex, procedure_code, scheduled_date, scheduled_time, "
                "source_message_id, study_description, study_instance_uid, status, mpps_instance_uid "
                "FROM worklist_items WHERE modality = ? ORDER BY scheduled_date, scheduled_time"
            ),
            ["CT"],
        )

        mock_connection.reset_mock()
        subject.find_worklist_items(scheduled_date="20240101")

        mock_connection.execute.assert_called_once_with(
            (
                "SELECT accession_number, modality, patient_birth_date, patient_id, "
                "patient_name, patient_sex, procedure_code, scheduled_date, scheduled_time, "
                "source_message_id, study_description, study_instance_uid, status, mpps_instance_uid "
                "FROM worklist_items WHERE scheduled_date = ? "
                "ORDER BY scheduled_date, scheduled_time"
            ),
            ["20240101"],
        )

        mock_connection.reset_mock()
        subject.find_worklist_items(modality="MG", scheduled_date="20240101", patient_id="999123456")

        mock_connection.execute.assert_called_once_with(
            (
                "SELECT accession_number, modality, patient_birth_date, patient_id, "
                "patient_name, patient_sex, procedure_code, scheduled_date, scheduled_time, "
                "source_message_id, study_description, study_instance_uid, status, mpps_instance_uid "
                "FROM worklist_items "
                "WHERE modality = ? AND scheduled_date = ? AND patient_id = ? "
                "ORDER BY scheduled_date, scheduled_time"
            ),
            ["MG", "20240101", "999123456"],
        )

    def test_get_worklist_item(self, mock_db, tmp_dir, result):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = result
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        worklist_item = subject.get_worklist_item("ACC123456")

        mock_connection.execute.assert_called_once_with(
            (
                "SELECT accession_number, modality, patient_birth_date, patient_id, "
                "patient_name, patient_sex, procedure_code, scheduled_date, scheduled_time, "
                "source_message_id, study_description, study_instance_uid, status, mpps_instance_uid "
                "FROM worklist_items WHERE accession_number = ?"
            ),
            ("ACC123456",),
        )
        assert worklist_item == WorklistItem(**result)

    def test_get_worklist_item_returns_none(self, mock_db, tmp_dir):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)

        assert subject.get_worklist_item("ACC123456") is None

    def test_update_status(self, mock_db, tmp_dir):
        mock_connection = MagicMock()
        mock_cursor = PropertyMock()
        mock_cursor.rowcount = 1
        mock_cursor.fetchone.return_value = {"source_message_id": "MSGID123456"}
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        result = subject.update_status("ACC123456", "COMPLETED")

        assert mock_connection.execute.call_count == 2
        mock_connection.execute.assert_any_call(
            """
                UPDATE worklist_items
                SET status = ?,
                    mpps_instance_uid = COALESCE(?, mpps_instance_uid),
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession_number = ?
            """,
            ("COMPLETED", None, "ACC123456"),
        )
        mock_connection.execute.assert_any_call(
            "SELECT source_message_id FROM worklist_items WHERE accession_number = ?", ("ACC123456",)
        )
        mock_connection.commit.assert_called_once()
        assert result == "MSGID123456"

    def test_update_status_with_no_update(self, mock_db, tmp_dir):
        mock_connection = MagicMock()
        mock_cursor = PropertyMock()
        mock_cursor.rowcount = 0
        mock_cursor.fetchone.return_value = {"source_message_id": "MSGID123456"}
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        subject.update_status("ACC123456", "COMPLETED")

        result = mock_connection.execute.assert_called_once_with(
            """
                UPDATE worklist_items
                SET status = ?,
                    mpps_instance_uid = COALESCE(?, mpps_instance_uid),
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession_number = ?
            """,
            ("COMPLETED", None, "ACC123456"),
        )
        mock_connection.commit.assert_called_once()
        assert result is None

    def test_update_status_with_mpps(self, mock_db, tmp_dir):
        mock_connection = MagicMock()
        mock_cursor = PropertyMock()
        mock_cursor.rowcount = 1
        mock_cursor.fetchone.return_value = {"source_message_id": "MSGID123456"}
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        result = subject.update_status("ACC123456", "COMPLETED", mpps_instance_uid="some-uid")
        assert mock_connection.execute.call_count == 2
        mock_connection.execute.assert_any_call(
            """
                UPDATE worklist_items
                SET status = ?,
                    mpps_instance_uid = COALESCE(?, mpps_instance_uid),
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession_number = ?
            """,
            ("COMPLETED", "some-uid", "ACC123456"),
        )
        mock_connection.commit.assert_called_once()
        assert result == "MSGID123456"

    def test_update_study_instance_uid(self, mock_db, tmp_dir):
        study_instance_uid = "some-uid"
        mock_connection = MagicMock()
        mock_cursor = PropertyMock()
        mock_cursor.rowcount = 1
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        result = subject.update_study_instance_uid("ACC123456", study_instance_uid)

        mock_connection.execute.assert_called_once_with(
            """
                UPDATE worklist_items
                SET study_instance_uid = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession_number = ?
            """,
            (study_instance_uid, "ACC123456"),
        )
        mock_connection.commit.assert_called_once()

        assert result is True

    def test_update_study_instance_uid_raises(self, mock_db, tmp_dir):
        study_instance_uid = "some-uid"
        mock_connection = MagicMock()
        mock_cursor = PropertyMock()
        mock_cursor.rowcount = 0
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        with pytest.raises(WorklistItemNotFoundError):
            subject.update_study_instance_uid("ACC123456", study_instance_uid)

    def test_delete_worklist_item(self, mock_db, tmp_dir):
        mock_connection = MagicMock()
        mock_cursor = PropertyMock()
        mock_cursor.rowcount = 1
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        result = subject.delete_worklist_item("ACC123456")

        mock_connection.execute.assert_called_once_with(
            "DELETE FROM worklist_items WHERE accession_number = ?", ("ACC123456",)
        )
        mock_connection.commit.assert_called_once()

        assert result is True

    def test_delete_worklist_item_raises(self, mock_db, tmp_dir):
        mock_connection = MagicMock()
        mock_cursor = PropertyMock()
        mock_cursor.rowcount = 0
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        with pytest.raises(WorklistItemNotFoundError):
            subject.delete_worklist_item("ACC123456")

    def test_mpps_instance_exists(self, mock_db, tmp_dir):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        assert subject.mpps_instance_exists(generate_uid()) is True

    def test_mpps_instance_not_exists(self, mock_db, tmp_dir):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        assert subject.mpps_instance_exists(generate_uid()) is False

    def test_get_worklist_item_by_mpps_instance_uid(self, mock_db, tmp_dir, result):
        mpps_instance_uid = "some-mpps-uid"
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = result
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)
        mock_connection.reset_mock()

        worklist_item = subject.get_worklist_item_by_mpps_instance_uid(mpps_instance_uid)

        mock_connection.execute.assert_called_once_with(
            (
                "SELECT accession_number, modality, patient_birth_date, patient_id, "
                "patient_name, patient_sex, procedure_code, scheduled_date, scheduled_time, "
                "source_message_id, study_description, study_instance_uid, status, mpps_instance_uid "
                "FROM worklist_items WHERE mpps_instance_uid = ?"
            ),
            (mpps_instance_uid,),
        )
        assert worklist_item == WorklistItem(**result)

    def test_get_worklist_item_by_mpps_instance_uid_returns_none(self, mock_db, tmp_dir):
        mpps_instance_uid = "some-mpps-uid"
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection

        subject = MWLStorage(tmp_dir)

        assert subject.get_worklist_item_by_mpps_instance_uid(mpps_instance_uid) is None
