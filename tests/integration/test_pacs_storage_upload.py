import pytest

from services.storage import MWLStorage, PACSStorage, WorklistItem


@pytest.fixture
def mwl_storage(tmp_path):
    """Create MWLStorage instance with temp database."""
    return MWLStorage(db_path=f"{tmp_path}/worklist.db")


@pytest.fixture
def pacs_storage(tmp_path):
    """Create PACSStorage instance with temp database."""
    return PACSStorage(db_path=f"{tmp_path}/pacs.db", storage_root=str(tmp_path / "storage"))


class TestPACSStorageUpload:
    def test_get_pending_uploads(self, pacs_storage):
        """Test retrieving pending uploads from database."""
        pacs_storage.store_instance("1.2.3.4", b"fake dicom", {})  # gitleaks:allow

        pending = pacs_storage.get_pending_uploads()
        assert len(pending) == 1
        assert pending[0]["sop_instance_uid"] == "1.2.3.4"  # gitleaks:allow

    def test_mark_upload_complete(self, pacs_storage):
        """Test marking upload as complete."""
        pacs_storage.store_instance("1.2.3.4", b"fake dicom", {})  # gitleaks:allow
        pacs_storage.mark_upload_started("1.2.3.4")  # gitleaks:allow

        pacs_storage.mark_upload_complete("1.2.3.4")  # gitleaks:allow

        with pacs_storage._get_connection() as conn:
            cursor = conn.execute(
                "SELECT upload_status, uploaded_at FROM stored_instances WHERE sop_instance_uid = ?",
                ("1.2.3.4",),  # gitleaks:allow
            )
            row = cursor.fetchone()

        assert row[0] == "COMPLETE"
        assert row[1] is not None  # uploaded_at timestamp set

    def test_mark_upload_failed_with_retry(self, pacs_storage):
        """Test marking upload as failed but retriable."""
        pacs_storage.store_instance("1.2.3.4", b"fake dicom", {})  # gitleaks:allow
        pacs_storage.mark_upload_started("1.2.3.4")  # gitleaks:allow

        pacs_storage.mark_upload_failed("1.2.3.4", "Network error", permanent=False)  # gitleaks:allow

        with pacs_storage._get_connection() as conn:
            cursor = conn.execute(
                "SELECT upload_status, upload_error FROM stored_instances WHERE sop_instance_uid = ?",
                ("1.2.3.4",),  # gitleaks:allow
            )
            row = cursor.fetchone()

        # Should go back to PENDING for retry
        assert row[0] == "PENDING"
        assert "Network error" in row[1]

    def test_mark_upload_failed_max_retries(self, pacs_storage):
        """Test marking upload as permanently failed after max retries."""
        pacs_storage.store_instance("1.2.3.4", b"fake dicom", {})  # gitleaks:allow
        # Simulate 3 failed upload attempts
        for _ in range(3):
            pacs_storage.mark_upload_started("1.2.3.4")  # gitleaks:allow
            pacs_storage.mark_upload_failed("1.2.3.4", "Error", permanent=False)  # gitleaks:allow
        pacs_storage.mark_upload_started("1.2.3.4")  # gitleaks:allow

        pacs_storage.mark_upload_failed("1.2.3.4", "Permanent error", permanent=True)  # gitleaks:allow

        with pacs_storage._get_connection() as conn:
            cursor = conn.execute(
                "SELECT upload_status FROM stored_instances WHERE sop_instance_uid = ?",
                ("1.2.3.4",),  # gitleaks:allow
            )
            row = cursor.fetchone()

        # Should be permanently FAILED
        assert row[0] == "FAILED"


class TestMWLStorageSourceMessageId:
    def test_get_source_message_id_found(self, mwl_storage):
        """Test retrieving source_message_id when it exists."""
        mwl_storage.store_worklist_item(
            WorklistItem(
                accession_number="ACC123",
                modality="MG",
                patient_birth_date="19800101",
                patient_id="NHS123",
                patient_name="DOE^JOHN",
                scheduled_date="20250101",
                scheduled_time="100000",
                source_message_id="ACTION456",
            )
        )

        result = mwl_storage.get_source_message_id("ACC123")

        assert result == "ACTION456"

    def test_get_source_message_id_not_found(self, mwl_storage):
        """Test retrieving source_message_id when accession number doesn't exist."""
        result = mwl_storage.get_source_message_id("NONEXISTENT")

        assert result is None

    def test_get_source_message_id_null(self, mwl_storage):
        """Test retrieving source_message_id when it's NULL in database."""
        mwl_storage.store_worklist_item(
            WorklistItem(
                accession_number="ACC123",
                modality="MG",
                patient_birth_date="19800101",
                patient_id="NHS123",
                patient_name="DOE^JOHN",
                scheduled_date="20250101",
                scheduled_time="100000",
                source_message_id=None,
            )
        )

        result = mwl_storage.get_source_message_id("ACC123")

        assert result is None
