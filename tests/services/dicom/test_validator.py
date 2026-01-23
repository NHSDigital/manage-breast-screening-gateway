import pytest
from pydicom import Dataset

from services.dicom.validator import DicomValidationError, DicomValidator

# Test UIDs for DICOM validation tests
TEST_SOP_INSTANCE_UID = "1.2.3.4.5"  # gitleaks:allow
TEST_STUDY_INSTANCE_UID = "1.2.3.4.5.6"  # gitleaks:allow
TEST_SOP_CLASS_UID = "1.2.840.10008.5.1.4.1.1.1.2"  # gitleaks:allow
TEST_PATIENT_ID = "123456"


class TestDicomValidator:
    @pytest.fixture
    def valid_dataset(self):
        ds = Dataset()
        ds.SOPInstanceUID = TEST_SOP_INSTANCE_UID
        ds.PatientID = TEST_PATIENT_ID
        ds.StudyInstanceUID = TEST_STUDY_INSTANCE_UID
        ds.SOPClassUID = TEST_SOP_CLASS_UID
        return ds

    @pytest.fixture
    def valid_image_dataset(self, valid_dataset):
        valid_dataset.PixelData = b"\x00" * 100
        valid_dataset.Rows = 10
        valid_dataset.Columns = 10
        valid_dataset.BitsAllocated = 8
        return valid_dataset

    def test_validate_dataset_success(self, valid_dataset):
        validator = DicomValidator()
        validator.validate_dataset(valid_dataset)  # Should not raise

    def test_validate_dataset_missing_sop_instance_uid(self):
        ds = Dataset()
        ds.PatientID = TEST_PATIENT_ID
        ds.StudyInstanceUID = TEST_STUDY_INSTANCE_UID
        ds.SOPClassUID = TEST_SOP_CLASS_UID

        validator = DicomValidator()
        with pytest.raises(DicomValidationError, match="Missing required tag: SOPInstanceUID"):
            validator.validate_dataset(ds)

    def test_validate_dataset_missing_patient_id(self):
        ds = Dataset()
        ds.SOPInstanceUID = TEST_SOP_INSTANCE_UID
        ds.StudyInstanceUID = TEST_STUDY_INSTANCE_UID
        ds.SOPClassUID = TEST_SOP_CLASS_UID

        validator = DicomValidator()
        with pytest.raises(DicomValidationError, match="Missing required tag: PatientID"):
            validator.validate_dataset(ds)

    def test_validate_dataset_missing_study_instance_uid(self):
        ds = Dataset()
        ds.SOPInstanceUID = TEST_SOP_INSTANCE_UID
        ds.PatientID = TEST_PATIENT_ID
        ds.SOPClassUID = TEST_SOP_CLASS_UID

        validator = DicomValidator()
        with pytest.raises(DicomValidationError, match="Missing required tag: StudyInstanceUID"):
            validator.validate_dataset(ds)

    def test_validate_dataset_missing_sop_class_uid(self):
        ds = Dataset()
        ds.SOPInstanceUID = TEST_SOP_INSTANCE_UID
        ds.PatientID = TEST_PATIENT_ID
        ds.StudyInstanceUID = TEST_STUDY_INSTANCE_UID

        validator = DicomValidator()
        with pytest.raises(DicomValidationError, match="Missing required tag: SOPClassUID"):
            validator.validate_dataset(ds)

    def test_validate_bytes_valid_preamble(self):
        # 128 bytes preamble + DICM + minimal content
        data = b"\x00" * 128 + b"DICM" + b"\x00" * 100

        validator = DicomValidator()
        validator.validate_bytes(data)  # Should not raise

    def test_validate_bytes_missing_preamble(self):
        # DICM at wrong position (no 128-byte preamble before it)
        data = b"DICM" + b"\x00" * 200

        validator = DicomValidator()
        with pytest.raises(DicomValidationError, match="Invalid DICOM prefix"):
            validator.validate_bytes(data)

    def test_validate_bytes_too_small(self):
        data = b"\x00" * 50

        validator = DicomValidator()
        with pytest.raises(DicomValidationError, match="too small"):
            validator.validate_bytes(data)

    def test_validate_bytes_wrong_magic(self):
        data = b"\x00" * 128 + b"XXXX" + b"\x00" * 100

        validator = DicomValidator()
        with pytest.raises(DicomValidationError, match="Invalid DICOM prefix"):
            validator.validate_bytes(data)

    def test_validate_pixel_data_valid(self, valid_image_dataset):
        validator = DicomValidator()
        validator.validate_pixel_data(valid_image_dataset)  # Should not raise

    def test_validate_pixel_data_missing_rows(self):
        ds = Dataset()
        ds.PixelData = b"\x00" * 100
        ds.Columns = 10
        ds.BitsAllocated = 8

        validator = DicomValidator()
        with pytest.raises(DicomValidationError, match="missing Rows"):
            validator.validate_pixel_data(ds)

    def test_validate_pixel_data_missing_columns(self):
        ds = Dataset()
        ds.PixelData = b"\x00" * 100
        ds.Rows = 10
        ds.BitsAllocated = 8

        validator = DicomValidator()
        with pytest.raises(DicomValidationError, match="missing Columns"):
            validator.validate_pixel_data(ds)

    def test_validate_pixel_data_missing_bits_allocated(self):
        ds = Dataset()
        ds.PixelData = b"\x00" * 100
        ds.Rows = 10
        ds.Columns = 10

        validator = DicomValidator()
        with pytest.raises(DicomValidationError, match="missing BitsAllocated"):
            validator.validate_pixel_data(ds)

    def test_validate_pixel_data_no_pixel_data(self):
        ds = Dataset()  # No PixelData

        validator = DicomValidator()
        validator.validate_pixel_data(ds)  # Should not raise

    def test_validate_pixel_data_none_pixel_data(self):
        ds = Dataset()
        ds.PixelData = None

        validator = DicomValidator()
        validator.validate_pixel_data(ds)  # Should not raise
