import hashlib
from pathlib import Path
from unittest.mock import PropertyMock

import pydicom
import pytest
from pydicom import Dataset, FileMetaDataset
from pydicom.uid import JPEG2000, ExplicitVRLittleEndian, generate_uid
from pynetdicom.sop_class import (
    DigitalMammographyXRayImageStorageForProcessing,
)

from models import WorklistItem
from services.dicom.c_store import SUCCESS, CStore
from services.storage import MWLStorage, PACSStorage


@pytest.mark.integration
class TestCStoreSavesMetadata:
    @pytest.fixture
    def mock_event(self):
        dataset = Dataset()
        dataset.AccessionNumber = "ABC123"
        dataset.PatientID = "9990001112"
        dataset.SOPInstanceUID = generate_uid()
        dataset.StudyInstanceUID = generate_uid()
        dataset.SOPClassUID = generate_uid()
        file_meta = FileMetaDataset()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        file_meta.MediaStorageSOPClassUID = DigitalMammographyXRayImageStorageForProcessing
        event = PropertyMock()
        event.file_meta = file_meta
        event.dataset = dataset
        event.assoc.requestor.ae_title = "ae-title"
        return event

    @pytest.fixture
    def storage(self, tmp_dir):
        return PACSStorage(f"{tmp_dir}/test.db", tmp_dir)

    @pytest.fixture
    def mwl_storage(self, tmp_dir):
        mwl = MWLStorage(f"{tmp_dir}/worklist.db")
        mwl.store_worklist_item(
            WorklistItem(
                accession_number="ABC123",
                modality="MG",
                patient_birth_date="19800101",
                patient_id="9990001112",
                patient_name="JANE^SMITH",
                scheduled_date="20240101",
                scheduled_time="090000",
                source_message_id="action-uuid-123",
            )
        )
        return mwl

    def storage_path(self, sop_instance_uid: str) -> str:
        hex = hashlib.sha256(sop_instance_uid.encode()).hexdigest()

        return f"{hex[:2]}/{hex[2:4]}/{hex[:16]}.dcm"

    def test_existing_sop_instance_uid(self, storage, mwl_storage, mock_event):
        """Existing SOP instance UID."""
        sop_instance_uid = mock_event.dataset.SOPInstanceUID
        subject = CStore(storage, mwl_storage)
        mock_event.dataset.file_meta = mock_event.file_meta
        storage.store_instance(
            sop_instance_uid,
            subject.dataset_to_bytes(mock_event.dataset),
            {"accession_number": "ABC123", "patient_id": "9990001112"},
            "ae-title",
        )

        assert subject.call(mock_event) == SUCCESS

        with storage._get_connection() as conn:
            cursor = conn.execute(
                """
                    SELECT patient_id
                    FROM   stored_instances
                    WHERE  sop_instance_uid = ?
                """,
                (sop_instance_uid,),
            )
            results = cursor.fetchall()

            assert len(results) == 1

    def test_valid_event_is_stored(self, storage, mwl_storage, mock_event):
        """Valid event is stored."""
        subject = CStore(storage, mwl_storage)

        assert subject.call(mock_event) == SUCCESS

        with storage._get_connection() as conn:
            cursor = conn.execute(
                """
                    SELECT patient_id, accession_number,
                           source_aet, storage_path
                    FROM   stored_instances
                    WHERE  sop_instance_uid = ?
                """,
                (mock_event.dataset.SOPInstanceUID,),
            )
            result = cursor.fetchone()

            assert result is not None
            patient_id, accession_number, source_aet, storage_path = result
            assert patient_id == "9990001112"
            assert accession_number == "ABC123"
            assert source_aet == "ae-title"
            assert storage_path == self.storage_path(mock_event.dataset.SOPInstanceUID)
            assert Path(f"{storage.storage_root}/{storage_path}").is_file()

    def test_c_store_marks_worklist_in_progress(self, storage, mwl_storage, mock_event):
        """C-STORE marks worklist in progress."""
        subject = CStore(storage, mwl_storage)
        assert subject.call(mock_event) == SUCCESS

        fetched = mwl_storage.get_worklist_item("ABC123")
        assert fetched.status == "IN PROGRESS"

    def test_compressed_image_stored_on_filesystem(self, storage, mwl_storage, dataset_with_pixels):
        """Verify compressed images are stored with JPEG 2000 transfer syntax."""
        sop_instance_uid = generate_uid()
        dataset_with_pixels.AccessionNumber = "ABC123"
        dataset_with_pixels.PatientID = "9990001112"
        dataset_with_pixels.SOPClassUID = DigitalMammographyXRayImageStorageForProcessing
        dataset_with_pixels.SOPInstanceUID = sop_instance_uid
        dataset_with_pixels.StudyInstanceUID = generate_uid()

        event = PropertyMock()
        event.file_meta = dataset_with_pixels.file_meta
        event.dataset = dataset_with_pixels
        event.assoc.requestor.ae_title = "test-ae"

        subject = CStore(storage, mwl_storage)
        assert subject.call(event) == SUCCESS

        with storage._get_connection() as conn:
            cursor = conn.execute(
                """
                    SELECT storage_path
                    FROM   stored_instances
                    WHERE  sop_instance_uid = ?
                """,
                (sop_instance_uid,),
            )
            result = cursor.fetchone()

        assert result is not None
        storage_path = result[0]
        stored_file = Path(storage.storage_root) / storage_path
        assert stored_file.exists()

        # Read with force=True since DicomFileLike doesn't write preamble
        stored_ds = pydicom.dcmread(stored_file, force=True)
        assert stored_ds.file_meta.TransferSyntaxUID == JPEG2000
