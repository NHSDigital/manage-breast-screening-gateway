import pytest
from pydicom import Dataset
from pynetdicom import AE
from pynetdicom.sop_class import ModalityWorklistInformationFind

from server import MWLServer
from services.dicom import PENDING, SUCCESS


@pytest.mark.integration
class TestRequestCFindOnWorklist:
    @pytest.fixture(autouse=True)
    def with_pacs_server(self, tmp_dir):
        server = MWLServer("MWL_SCP", 4243, f"{tmp_dir}/test.db", block=False)
        storage = server.storage
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

        server.start()

        yield

        server.stop()

    def test_cfind_request_to_worklist_server(self):
        ae = AE(ae_title="LOCAL_AE_TITLE")
        ae.add_requested_context(ModalityWorklistInformationFind)
        assoc = ae.associate("0.0.0.0", 4243, ae_title="MWL_SCP_AE_TITLE")

        assert assoc.is_established
        query = Dataset()
        query.QueryRetrieveLevel = "SCHEDULED"

        responses = list(assoc.send_c_find(query, query_model=ModalityWorklistInformationFind))
        assert len(responses) == 3

        status, ds = responses[0]
        assert status.Status == PENDING
        assert ds.PatientID == "999123456"
        assert ds.PatientName == "SMITH^JANE"
        assert ds.AccessionNumber == "ACC123456"

        status, ds = responses[1]
        assert status.Status == PENDING
        assert ds.PatientID == "999234567"
        assert ds.PatientName == "JONES^MARY"
        assert ds.AccessionNumber == "ACC234567"

        status, ds = responses[2]
        assert status.Status == SUCCESS
        assert ds is None

    def test_cfind_with_filters_request_to_worklist_server(self):
        ae = AE(ae_title="LOCAL_AE_TITLE")
        ae.add_requested_context(ModalityWorklistInformationFind)
        assoc = ae.associate("0.0.0.0", 4243, ae_title="MWL_SCP_AE_TITLE")

        assert assoc.is_established
        query = Dataset()
        query.QueryRetrieveLevel = "SCHEDULED"
        query.ScheduledProcedureStepSequence = [Dataset()]
        query.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate = "20240102"
        query.AccessionNumber = ""
        query.Modality = "MG"

        responses = list(assoc.send_c_find(query, query_model=ModalityWorklistInformationFind))
        assert len(responses) == 2

        status, ds = responses[0]
        assert status.Status == PENDING
        assert ds.PatientID == "999234567"
        assert ds.PatientName == "JONES^MARY"
        assert ds.AccessionNumber == "ACC234567"

        status, ds = responses[1]
        assert status.Status == SUCCESS
        assert ds is None
