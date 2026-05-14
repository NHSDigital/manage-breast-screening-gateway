from unittest.mock import MagicMock, patch

import pytest
from pydicom.dataset import Dataset
from pydicom.uid import DigitalMammographyXRayImageStorageForPresentation, ExplicitVRLittleEndian, generate_uid

from modality_emulator import (
    DICOM_LATERALITIES,
    DICOM_VIEWS,
    DicomExample,
    ModalityEmulator,
    main,
)


class TestDicomExample:
    @patch("modality_emulator.Image.open")
    @patch("modality_emulator.generate_uid")
    def test_generate_dicom_creates_valid_dataset(
        self,
        mock_generate_uid,
        mock_image_open,
    ):
        study_instance_uid = generate_uid()
        sop_instance_uid = generate_uid()
        implementation_class_uid = generate_uid()
        series_instance_uid = generate_uid()

        mock_generate_uid.side_effect = [
            sop_instance_uid,
            implementation_class_uid,
            series_instance_uid,
        ]

        mock_image = MagicMock()
        mock_image.convert.return_value = mock_image
        mock_image.size = (100, 200)

        mock_image_open.return_value = mock_image

        ds = Dataset()
        ds.AccessionNumber = "ACC123"
        ds.PatientID = "PAT001"
        ds.PatientName = "Jane^Doe"
        ds.PatientBirthDate = "19800101"
        ds.PatientSex = "F"
        sps = Dataset()
        sps.ScheduledProcedureStepStartDate = "20260514"
        sps.ScheduledProcedureStepStartTime = "090000"
        ds.ScheduledProcedureStepSequence = [sps]

        with patch("modality_emulator.np.array") as mock_np_array:
            mock_pixel_array = MagicMock()
            mock_pixel_array.tobytes.return_value = b"\x01\x02"
            mock_np_array.return_value = mock_pixel_array

            dicom = DicomExample(
                dataset=ds,
                laterality="L",
                view="CC",
                study_instance_uid=study_instance_uid,
                series_number=1,
            )

        assert isinstance(dicom.data, Dataset)
        assert dicom.data.PatientID == "PAT001"
        assert dicom.data.PatientName == "Jane^Doe"
        assert dicom.data.ImageLaterality == "L"
        assert dicom.data.ViewPosition == "CC"
        assert dicom.data.Rows == 200
        assert dicom.data.Columns == 100
        assert dicom.data.StudyInstanceUID == study_instance_uid
        assert dicom.data.SOPInstanceUID == sop_instance_uid
        assert dicom.data.SeriesInstanceUID == series_instance_uid
        assert dicom.data.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian
        assert dicom.data.file_meta.ImplementationClassUID == implementation_class_uid
        assert dicom.data.file_meta.MediaStorageSOPClassUID == DigitalMammographyXRayImageStorageForPresentation
        assert dicom.data.file_meta.MediaStorageSOPInstanceUID == sop_instance_uid
        assert dicom.data.StudyDate == "20260514"
        assert dicom.data.StudyTime == "090000"


class TestModalityEmulator:
    @pytest.fixture
    def pending_status(self):
        status = Dataset()
        status.Status = 0xFF00
        return status

    @pytest.fixture
    def success_status(self):
        status = Dataset()
        status.Status = 0x0000
        return status

    @patch("modality_emulator.time.sleep")
    @patch("modality_emulator.generate_uid")
    @patch("modality_emulator.DicomExample")
    def test_process_worklist_items_sends_all_dicoms(
        self,
        mock_dicom_example,
        mock_generate_uid,
        _,
        pending_status,
        success_status,
    ):
        mock_generate_uid.return_value = "1.2.3.study"  # gitleaks: ignore

        mwl_storage = MagicMock()
        pacs_storage = MagicMock()

        emulator = ModalityEmulator(mwl_storage, pacs_storage)

        ds = Dataset()
        ds.SOPInstanceUID = generate_uid()
        ds.AccessionNumber = "ACC123"
        ds.PatientID = "PAT001"
        ds.PatientName = "Jane^Doe"
        ds.PatientSex = "F"
        sps = Dataset()
        sps.ScheduledProcedureStepStartDate = "20260514"
        sps.ScheduledProcedureStepStartTime = "090000"
        ds.ScheduledProcedureStepSequence = [sps]

        mock_dicom_example.return_value.data = ds

        mwl_assoc = MagicMock()
        mwl_assoc.is_established = True
        mwl_assoc.send_c_find.return_value = [(pending_status, ds), (success_status, None)]

        pacs_assoc = MagicMock()
        pacs_assoc.is_established = True

        ae = MagicMock()
        ae.associate.side_effect = [mwl_assoc, pacs_assoc]

        emulator.process_worklist_items(ae)

        expected_send_count = len(DICOM_LATERALITIES) * len(DICOM_VIEWS)

        assert mwl_assoc.send_c_find.call_count == 1
        assert pacs_assoc.send_c_store.call_count == expected_send_count

        mwl_storage.update_status.assert_called_once_with(
            "ACC123",
            "COMPLETED",
        )

        mwl_assoc.release.assert_called_once()
        pacs_assoc.release.assert_called_once()

    @patch("modality_emulator.time.sleep")
    def test_process_worklist_items_returns_when_no_items(
        self,
        mock_sleep,
        success_status,
    ):
        mwl_storage = MagicMock()
        pacs_storage = MagicMock()
        emulator = ModalityEmulator(mwl_storage, pacs_storage)
        ae = MagicMock()

        mwl_assoc = MagicMock()
        mwl_assoc.is_established = True
        mwl_assoc.send_c_find.return_value = [(success_status, None)]

        pacs_assoc = MagicMock()
        pacs_assoc.is_established = True

        ae = MagicMock()
        ae.associate.side_effect = [mwl_assoc, pacs_assoc]

        emulator.process_worklist_items(ae)

        mock_sleep.assert_not_called()
        pacs_assoc.send_c_store.assert_not_called()
        mwl_storage.update_status.assert_not_called()
        mwl_assoc.release.assert_called_once()
        pacs_assoc.release.assert_called_once()

    @patch("modality_emulator.time.sleep")
    def test_process_worklist_items_handles_failed_association(
        self,
        _,
    ):
        mwl_storage = MagicMock()
        pacs_storage = MagicMock()

        emulator = ModalityEmulator(mwl_storage, pacs_storage)

        mwl_assoc = MagicMock()
        mwl_assoc.is_established = True

        pacs_assoc = MagicMock()
        pacs_assoc.is_established = False

        ae = MagicMock()
        ae.associate.side_effect = [mwl_assoc, pacs_assoc]

        emulator.process_worklist_items(ae)

        mwl_assoc.send_c_find.assert_not_called()
        pacs_assoc.send_c_store.assert_not_called()
        mwl_storage.update_status.assert_not_called()
        mwl_assoc.release.assert_called_once()
        pacs_assoc.release.assert_called_once()

    @patch("modality_emulator.Environment", production=True)
    def test_main_raises_in_production(self, _):
        with pytest.raises(RuntimeError, match="Modality Emulator should not be run in production environment"):
            main()
