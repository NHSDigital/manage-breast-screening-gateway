"""Tests for C-FIND worklist handler."""

from unittest.mock import Mock

import pytest
from pydicom import Dataset

from services.dicom import FAILURE, PENDING, SUCCESS
from services.mwl.c_find import CFindHandler
from services.storage import WorklistItem


@pytest.fixture
def mock_storage():
    return Mock()


@pytest.fixture
def handler(mock_storage):
    return CFindHandler(mock_storage)


@pytest.fixture
def mock_event():
    event = Mock()
    event.identifier = Dataset()
    event.assoc.requestor.ae_title = "TEST_SCU"
    return event


@pytest.fixture
def sample_worklist_item():
    return {
        "accession_number": "ACC001",
        "patient_id": "9876543210",
        "patient_name": "TEST^PATIENT",
        "patient_birth_date": "19800101",
        "patient_sex": "F",
        "scheduled_date": "20260107",
        "scheduled_time": "100000",
        "modality": "MG",
        "study_description": "Bilateral Screening Mammogram",
        "procedure_code": "PROC001",
        "study_instance_uid": "1.2.3.4.5",  # gitleaks:allow
        "status": "SCHEDULED",
    }


class TestCFindHandler:
    """Tests for CFindHandler class."""

    def test_call_with_no_results(self, handler, mock_storage, mock_event):
        mock_storage.find_worklist_items.return_value = []

        results = list(handler.call(mock_event))

        assert len(results) == 1
        status, ds = results[0]
        assert status == SUCCESS
        assert ds is None
        mock_storage.find_worklist_items.assert_called_once()

    def test_call_with_single_result(self, handler, mock_storage, mock_event, sample_worklist_item):
        worklist_item = WorklistItem(**sample_worklist_item)
        mock_storage.find_worklist_items.return_value = [worklist_item]

        results = list(handler.call(mock_event))

        assert len(results) == 2
        # First result: pending with dataset
        status, ds = results[0]
        assert status == PENDING
        assert isinstance(ds, Dataset)
        assert ds.PatientID == "9876543210"
        assert ds.AccessionNumber == "ACC001"
        # Final result: success
        status, ds = results[1]
        assert status == SUCCESS
        assert ds is None

    def test_call_with_multiple_results(self, handler, mock_storage, mock_event):
        items = [
            WorklistItem(
                accession_number=f"ACC00{i}",
                patient_id=f"PT{i}",
                patient_name=f"TEST^PATIENT{i}",
                patient_birth_date="19800101",
                patient_sex="F",
                scheduled_date="20260107",
                scheduled_time="100000",
                modality="MG",
                study_description="Test",
                procedure_code="PROC001",
            )
            for i in range(3)
        ]
        mock_storage.find_worklist_items.return_value = items

        results = list(handler.call(mock_event))

        # 3 pending results + 1 success
        assert len(results) == 4
        for i in range(3):
            status, ds = results[i]
            assert status == PENDING
            assert ds.AccessionNumber == f"ACC00{i}"
        status, ds = results[3]
        assert status == SUCCESS

    def test_call_with_modality_filter(self, handler, mock_storage, mock_event):
        # Add modality to query
        sps_item = Dataset()
        sps_item.Modality = "MG"
        mock_event.identifier.ScheduledProcedureStepSequence = [sps_item]
        mock_storage.find_worklist_items.return_value = []

        list(handler.call(mock_event))

        mock_storage.find_worklist_items.assert_called_once_with(
            modality="MG", scheduled_date=None, patient_id=None, status="SCHEDULED"
        )

    def test_call_with_date_filter(self, handler, mock_storage, mock_event):
        sps_item = Dataset()
        sps_item.ScheduledProcedureStepStartDate = "20260107"
        mock_event.identifier.ScheduledProcedureStepSequence = [sps_item]
        mock_storage.find_worklist_items.return_value = []

        list(handler.call(mock_event))

        mock_storage.find_worklist_items.assert_called_once_with(
            modality=None, scheduled_date="20260107", patient_id=None, status="SCHEDULED"
        )

    def test_call_with_patient_id_filter(self, handler, mock_storage, mock_event):
        mock_event.identifier.PatientID = "9876543210"
        mock_storage.find_worklist_items.return_value = []

        list(handler.call(mock_event))

        mock_storage.find_worklist_items.assert_called_once_with(
            modality=None, scheduled_date=None, patient_id="9876543210", status="SCHEDULED"
        )

    def test_call_handles_storage_exception(self, handler, mock_storage, mock_event):
        mock_storage.find_worklist_items.side_effect = Exception("Database error")

        results = list(handler.call(mock_event))

        assert len(results) == 1
        status, ds = results[0]
        assert status == FAILURE
        assert ds is None

    def test_build_worklist_response_missing_optional_fields(self, handler):
        minimal_item = WorklistItem(
            accession_number="ACC001",
            patient_id="9876543210",
            patient_name="TEST^PATIENT",
            patient_birth_date="19800101",
            scheduled_date="20260107",
            scheduled_time="100000",
            modality="MG",
        )

        ds = handler._build_worklist_response(minimal_item)

        # Required fields present
        assert ds.PatientID == "9876543210"
        assert ds.AccessionNumber == "ACC001"
        # Optional fields absent
        assert not hasattr(ds, "PatientSex")
        assert not hasattr(ds, "StudyInstanceUID")
        assert not hasattr(ds, "StudyDescription")
