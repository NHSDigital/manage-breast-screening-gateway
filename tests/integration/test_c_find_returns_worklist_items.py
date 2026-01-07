from unittest.mock import PropertyMock

import pytest
from pydicom import Dataset

from services.dicom import PENDING, SUCCESS
from services.mwl.c_find import CFindHandler
from services.storage import WorklistStorage


@pytest.mark.integration
class TestCFindReturnsWorklistItems:
    @pytest.fixture
    def storage(self, tmp_dir):
        return WorklistStorage(f"{tmp_dir}/test.db")

    @pytest.fixture(autouse=True)
    def with_worklist_items(self, storage):
        storage.store_worklist_item(
            accession_number="ACC123456",
            patient_id="999123456",
            patient_name="SMITH^JANE",
            patient_birth_date="19800101",
            patient_sex="F",
            scheduled_date="20240101",
            scheduled_time="090000",
            modality="MG",
            study_description="MAMMOGRAPHY",
        )
        storage.update_status("ACC123456", "SCHEDULED")
        storage.store_worklist_item(
            accession_number="ACC234567",
            patient_id="999234567",
            patient_name="JONES^MARY",
            patient_birth_date="19900202",
            patient_sex="F",
            scheduled_date="20240102",
            scheduled_time="094500",
            modality="MG",
            study_description="MAMMOGRAPHY",
        )
        storage.update_status("ACC234567", "SCHEDULED")

        yield storage

    @pytest.fixture
    def event(self):
        dataset = Dataset()
        sps = Dataset()
        dataset.ScheduledProcedureStepSequence = [sps]
        event = PropertyMock()
        event.assoc.requestor.ae_title = "ae-title"
        event.identifier = dataset
        return event

    def test_cfind_returns_scheduled_items(self, event, storage):
        results = list(CFindHandler(storage).call(event))
        assert len(results) == 3

        status, ds = results[0]
        assert status == PENDING
        assert ds.PatientID == "999123456"
        assert ds.PatientName == "SMITH^JANE"
        assert ds.PatientBirthDate == "19800101"
        assert ds.PatientSex == "F"
        assert ds.AccessionNumber == "ACC123456"
        assert ds.StudyDescription == "MAMMOGRAPHY"
        assert ds.ScheduledProcedureStepSequence[0].Modality == "MG"
        assert ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepDescription == "MAMMOGRAPHY"
        assert ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate == "20240101"
        assert ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartTime == "090000"

        status, ds = results[1]
        assert status == PENDING
        assert ds.PatientID == "999234567"
        assert ds.PatientName == "JONES^MARY"
        assert ds.PatientBirthDate == "19900202"
        assert ds.PatientSex == "F"
        assert ds.AccessionNumber == "ACC234567"
        assert ds.StudyDescription == "MAMMOGRAPHY"
        assert ds.ScheduledProcedureStepSequence[0].Modality == "MG"
        assert ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepDescription == "MAMMOGRAPHY"
        assert ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate == "20240102"
        assert ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartTime == "094500"

        status, ds = results[2]
        assert status == SUCCESS
        assert ds is None

    def test_cfind_filters_by_scheduled_date(self, event, storage):
        event.identifier.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate = "20240101"

        results = list(CFindHandler(storage).call(event))

        assert len(results) == 2

        status, ds = results[0]
        assert status == PENDING
        assert ds.PatientID == "999123456"
        assert ds.PatientName == "SMITH^JANE"
        assert ds.PatientBirthDate == "19800101"
        assert ds.AccessionNumber == "ACC123456"
        assert ds.ScheduledProcedureStepSequence[0].Modality == "MG"
        assert ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate == "20240101"

        status, ds = results[1]
        assert status == SUCCESS
        assert ds is None

    def test_cfind_filters_by_modality(self, event, storage):
        storage.store_worklist_item(
            accession_number="ACC999999",
            patient_id="999234567",
            patient_name="JONES^MARY",
            patient_birth_date="19900202",
            patient_sex="F",
            scheduled_date="20240101",
            scheduled_time="094500",
            modality="CT",
        )
        storage.update_status("ACC234567", "SCHEDULED")

        event.identifier.ScheduledProcedureStepSequence[0].Modality = "MG"

        results = list(CFindHandler(storage).call(event))

        assert len(results) == 3

        status, ds = results[0]
        assert status == PENDING
        assert ds.PatientID == "999123456"
        assert ds.PatientName == "SMITH^JANE"
        status, ds = results[1]
        assert status == PENDING
        assert ds.PatientID == "999234567"
        assert ds.PatientName == "JONES^MARY"
        status, ds = results[2]
        assert status == SUCCESS
        assert ds is None

    def test_cfind_filters_by_patient_id(self, event, storage):
        event.identifier.PatientID = "999234567"

        results = list(CFindHandler(storage).call(event))

        assert len(results) == 2

        status, ds = results[0]
        assert status == PENDING
        assert ds.PatientID == "999234567"
        assert ds.PatientName == "JONES^MARY"
        assert ds.AccessionNumber == "ACC234567"

        status, ds = results[1]
        assert status == SUCCESS
        assert ds is None
