import hashlib
import os
from pathlib import Path
from shutil import rmtree
from threading import Lock
from unittest.mock import MagicMock, patch

from services.storage import PACSStorage

tmp_dir = f"{os.path.dirname(os.path.realpath(__file__))}/tmp"


@patch("services.storage.sqlite3")
class TestStorage:
    def test_init(self, mock_db):
        mock_connection = MagicMock()
        mock_db.connect.return_value = mock_connection
        subject = PACSStorage(tmp_dir, tmp_dir)

        assert subject.db_path == tmp_dir
        assert subject.storage_root == Path(tmp_dir)
        assert isinstance(subject._lock, Lock)

        assert mock_connection.execute.call_count == 3
        mock_connection.execute.assert_any_call("PRAGMA journal_mode=WAL")
        mock_connection.execute.assert_any_call("PRAGMA synchronous=NORMAL")
        mock_connection.commit.assert_called_once()

    def test_instance_exists_returns_true(self, mock_db):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection
        subject = PACSStorage(tmp_dir, tmp_dir)
        mock_connection.reset_mock()

        assert subject.instance_exists("1.2.3.4.5.6") is True

        mock_connection.execute.assert_called_once_with(
            "SELECT 1 FROM stored_instances WHERE sop_instance_uid = ? AND status = 'STORED'", ("1.2.3.4.5.6",)
        )

    def test_instance_exists_returns_false(self, mock_db):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_connection = MagicMock()
        mock_connection.execute.return_value = mock_cursor
        mock_db.connect.return_value = mock_connection
        subject = PACSStorage(tmp_dir, tmp_dir)
        mock_connection.reset_mock()

        assert subject.instance_exists("1.2.3.4.5.6") is False

    def test_store_instance_saves_to_filesystem(self, mock_db):
        sop_instance_uid = "1.2.3.4.5.6"
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

        rmtree(tmp_dir)

    def test_store_instance_saves_to_db(self, mock_db):
        mock_connection = MagicMock()
        mock_db.connect.return_value = mock_connection
        subject = PACSStorage(tmp_dir, tmp_dir)
        subject.instance_exists = MagicMock(return_value=False)
        mock_connection.reset_mock()

        # TODO: More
        metadata = {"patient_id": "9990001112", "patient_name": "SMITH^JANE"}

        subject.store_instance(
            "1.2.3.4.5.6",
            b"foo",
            metadata,
        )

        # FIXME: This assertion is whitespace sensitive
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
                "1.2.3.4.5.6",
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

        # Clean up
        rmtree(tmp_dir)
