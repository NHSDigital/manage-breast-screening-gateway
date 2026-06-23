"""Tests for C-FIND worklist handler."""

from unittest.mock import Mock

import pytest
from pydicom import Dataset

from services.dicom import CHARSET_UTF8, FAILURE, PENDING, SUCCESS
from services.mwl.c_find import CFind
from services.storage import WorklistItem


@pytest.fixture
def mock_storage():
    return Mock()


@pytest.fixture
def handler(mock_storage):
    return CFind(mock_storage)


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


class TestCFind:
    """Tests for CFind class."""

    def test_call_with_no_results(self, handler, mock_storage, mock_event):
        """C-FIND: Call with no results."""
        mock_storage.find_worklist_items.return_value = []

        results = list(handler.call(mock_event))

        assert len(results) == 1
        status, ds = results[0]
        assert status == SUCCESS
        assert ds is None
        mock_storage.find_worklist_items.assert_called_once()

    def test_call_with_single_result(self, handler, mock_storage, mock_event, sample_worklist_item):
        """C-FIND: Call with single result."""
        worklist_item = WorklistItem(**sample_worklist_item)
        mock_storage.find_worklist_items.return_value = [worklist_item]

        results = list(handler.call(mock_event))

        assert len(results) == 2
        # First result: pending with dataset
        status, ds = results[0]
        assert status == PENDING
        assert isinstance(ds, Dataset)
        assert ds.SpecificCharacterSet == CHARSET_UTF8
        assert ds.PatientID == "9876543210"
        assert ds.AccessionNumber == "ACC001"
        # Final result: success
        status, ds = results[1]
        assert status == SUCCESS
        assert ds is None

    def test_call_with_multiple_results(self, handler, mock_storage, mock_event):
        """C-FIND: Call with multiple results."""
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

    def test_call_with_accession_number_filter(self, handler, mock_storage, mock_event):
        """C-FIND: Call with accession number filter."""
        mock_event.identifier.AccessionNumber = "ACC12345"
        mock_storage.find_worklist_items.return_value = []

        list(handler.call(mock_event))

        mock_storage.find_worklist_items.assert_called_once_with(
            accession_number="ACC12345",
            modality=None,
            scheduled_date=None,
            scheduled_time=None,
            patient_id=None,
            patient_name=None,
        )

    def test_call_with_modality_filter(self, handler, mock_storage, mock_event):
        # Add modality to query
        """C-FIND: Call with modality filter."""
        sps_item = Dataset()
        sps_item.Modality = "MG"
        mock_event.identifier.ScheduledProcedureStepSequence = [sps_item]
        mock_storage.find_worklist_items.return_value = []

        list(handler.call(mock_event))

        mock_storage.find_worklist_items.assert_called_once_with(
            accession_number=None,
            modality="MG",
            scheduled_date=None,
            scheduled_time=None,
            patient_id=None,
            patient_name=None,
        )

    def test_call_with_date_filter(self, handler, mock_storage, mock_event):
        """C-FIND: Call with date filter."""
        sps_item = Dataset()
        sps_item.ScheduledProcedureStepStartDate = "20260107"
        mock_event.identifier.ScheduledProcedureStepSequence = [sps_item]
        mock_storage.find_worklist_items.return_value = []

        list(handler.call(mock_event))

        mock_storage.find_worklist_items.assert_called_once_with(
            accession_number=None,
            modality=None,
            scheduled_date="20260107",
            scheduled_time=None,
            patient_id=None,
            patient_name=None,
        )

    def test_call_with_time_filter(self, handler, mock_storage, mock_event):
        """C-FIND: Call with time filter."""
        sps_item = Dataset()
        sps_item.ScheduledProcedureStepStartTime = "100000"
        mock_event.identifier.ScheduledProcedureStepSequence = [sps_item]
        mock_storage.find_worklist_items.return_value = []

        list(handler.call(mock_event))

        mock_storage.find_worklist_items.assert_called_once_with(
            accession_number=None,
            scheduled_time="100000",
            modality=None,
            scheduled_date=None,
            patient_id=None,
            patient_name=None,
        )

    def test_call_with_patient_id_filter(self, handler, mock_storage, mock_event):
        """C-FIND: Call with patient id filter."""
        mock_event.identifier.PatientID = "9876543210"
        mock_storage.find_worklist_items.return_value = []

        list(handler.call(mock_event))

        mock_storage.find_worklist_items.assert_called_once_with(
            accession_number=None,
            modality=None,
            scheduled_time=None,
            scheduled_date=None,
            patient_id="9876543210",
            patient_name=None,
        )

    def test_call_with_patient_name_filter(self, handler, mock_storage, mock_event):
        """C-FIND: Call with patient name filter."""
        mock_event.identifier.PatientName = "Smith*"
        mock_storage.find_worklist_items.return_value = []

        list(handler.call(mock_event))

        mock_storage.find_worklist_items.assert_called_once_with(
            accession_number=None,
            modality=None,
            scheduled_date=None,
            scheduled_time=None,
            patient_id=None,
            patient_name="Smith*",
        )

    def test_call_handles_storage_exception(self, handler, mock_storage, mock_event):
        """C-FIND: Call handles storage exception."""
        mock_storage.find_worklist_items.side_effect = Exception("Database error")

        results = list(handler.call(mock_event))

        assert len(results) == 1
        status, ds = results[0]
        assert status == FAILURE
        assert ds is None

    def test_call_return_key_attributes_present(self, handler, mock_storage, mock_event, sample_worklist_item):
        """C-FIND: Call return key attributes present."""
        worklist_item = WorklistItem(**sample_worklist_item)
        mock_storage.find_worklist_items.return_value = [worklist_item]

        results = list(handler.call(mock_event))

        assert len(results) == 2
        status, ds = results[0]
        assert status == PENDING
        assert ds.PatientID == "9876543210"
        assert ds.AccessionNumber == "ACC001"
        assert ds.PatientName == "TEST^PATIENT"
        assert ds.PatientBirthDate == "19800101"

        assert ds.PatientAddress is None
        assert ds.PatientComments is None
        assert ds.PatientWeight is None
        assert ds.PatientAge is None
        assert ds.PatientSex == "F"

        assert ds.StudyDescription == "Bilateral Screening Mammogram"
        assert ds.StudyInstanceUID == "1.2.3.4.5"  # gitleaks:allow

        scheduled_procedure_step = ds.ScheduledProcedureStepSequence[0]

        assert scheduled_procedure_step.Modality == "MG"
        assert scheduled_procedure_step.ScheduledProcedureStepStartDate == "20260107"
        assert scheduled_procedure_step.ScheduledProcedureStepStartTime == "100000"
        assert scheduled_procedure_step.ScheduledProcedureStepID == "PROC001"
        assert scheduled_procedure_step.ScheduledStationAETitle is None
        assert scheduled_procedure_step.ScheduledStationName is None
        assert scheduled_procedure_step.ScheduledProtocolCodeSequence[0].CodeValue is None
        assert scheduled_procedure_step.ScheduledProtocolCodeSequence[0].CodingSchemeDesignator is None
        assert scheduled_procedure_step.ScheduledProtocolCodeSequence[0].CodeMeaning is None

        assert ds.ReasonForRequestedProcedureCodeSequence[0].CodeValue is None
        assert ds.ReasonForRequestedProcedureCodeSequence[0].CodingSchemeDesignator is None
        assert ds.ReasonForRequestedProcedureCodeSequence[0].CodeMeaning is None

        assert ds.RequestedProcedureCodeSequence[0].CodeValue == "PROC001"
        assert ds.RequestedProcedureCodeSequence[0].CodingSchemeDesignator is None
        assert ds.RequestedProcedureCodeSequence[0].CodeMeaning is None
