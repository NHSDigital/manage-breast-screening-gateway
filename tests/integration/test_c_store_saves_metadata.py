from pathlib import Path
from unittest.mock import PropertyMock

import pydicom
import pytest
from pydicom import Dataset, FileMetaDataset
from pydicom.uid import JPEG2000, ExplicitVRLittleEndian
from pynetdicom.sop_class import (
    DigitalMammographyXRayImageStorageForProcessing,
)

from services.dicom.c_store import SUCCESS, CStore
from services.storage import PACSStorage


@pytest.mark.integration
class TestCStoreSavesMetadata:
    @pytest.fixture
    def mock_event(self):
        dataset = Dataset()
        dataset.AccessionNumber = "ABC123"
        dataset.PatientID = "9990001112"
        dataset.SOPInstanceUID = "1.2.3.4.5.6"
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

    def test_existing_sop_instance_uid(self, storage, mock_event):
        sop_instance_uid = "1.2.3.4.5.6"
        subject = CStore(storage)
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
                    WHERE  sop_instance_uid = '1.2.3.4.5.6'
                """
            )
            results = cursor.fetchall()

            assert len(results) == 1

    def test_valid_event_is_stored(self, storage, mock_event):
        subject = CStore(storage)

        assert subject.call(mock_event) == SUCCESS

        with storage._get_connection() as conn:
            cursor = conn.execute(
                """
                    SELECT patient_id, accession_number,
                           source_aet, storage_path
                    FROM   stored_instances
                    WHERE  sop_instance_uid = '1.2.3.4.5.6'
                """
            )
            result = cursor.fetchone()

            assert result is not None
            patient_id, accession_number, source_aet, storage_path = result
            assert patient_id == "9990001112"
            assert accession_number == "ABC123"
            assert source_aet == "ae-title"
            assert storage_path == "ff/af/ffaff041ab509297.dcm"
            assert Path(f"{storage.storage_root}/{storage_path}").is_file()

    def test_compressed_image_stored_on_filesystem(self, storage, dataset_with_pixels):
        """Verify compressed images are stored with JPEG 2000 transfer syntax."""
        # Customize the shared dataset for this test
        dataset_with_pixels.AccessionNumber = "DEF456"
        dataset_with_pixels.PatientID = "9990002223"
        dataset_with_pixels.SOPInstanceUID = "1.2.3.4.5.7"

        # Wrap in PropertyMock to simulate DICOM event
        event = PropertyMock()
        event.file_meta = dataset_with_pixels.file_meta
        event.dataset = dataset_with_pixels
        event.assoc.requestor.ae_title = "test-ae"

        subject = CStore(storage)
        assert subject.call(event) == SUCCESS

        # Verify stored file has JPEG 2000 compression
        with storage._get_connection() as conn:
            cursor = conn.execute(
                """
                    SELECT storage_path
                    FROM   stored_instances
                    WHERE  sop_instance_uid = '1.2.3.4.5.7'
                """
            )
            result = cursor.fetchone()

        assert result is not None
        storage_path = result[0]
        stored_file = Path(storage.storage_root) / storage_path
        assert stored_file.exists()

        # Read with force=True since DicomFileLike doesn't write preamble
        stored_ds = pydicom.dcmread(stored_file, force=True)
        assert stored_ds.file_meta.TransferSyntaxUID == JPEG2000
