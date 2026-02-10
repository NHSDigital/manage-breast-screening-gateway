import datetime

import pytest
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid
from pynetdicom import AE
from pynetdicom.sop_class import ModalityPerformedProcedureStep  # pyright: ignore[reportAttributeAccessIssue]

from server import MWLServer
from services.dicom import SUCCESS
from services.storage import MWLStorage, WorklistItem


class TestNSetUpdatesWorklistStatus:
    @pytest.fixture(autouse=True)
    def with_mwl_server(self, tmp_dir):
        server = MWLServer("SCREENING_MWL", 4243, f"{tmp_dir}/test.db", block=False)
        server.start()

        yield

        server.stop()

    @pytest.fixture
    def mpps_instance_uid(self):
        return generate_uid()

    @pytest.fixture
    def worklist_item(self):
        return WorklistItem(
            accession_number="ACC123",
            patient_id="999123456",
            patient_name="SMITH^JANE",
            patient_birth_date="19800101",
            patient_sex="F",
            scheduled_date="20240101",
            scheduled_time="090000",
            modality="MG",
            procedure_code="12345-6",
            study_description="MAMMOGRAPHY SCREENING",
            study_instance_uid=generate_uid(),
            source_message_id="MSGID123456",
        )

    def test_n_set_updates_worklist_status(self, tmp_dir, worklist_item, mpps_instance_uid):
        storage = MWLStorage(f"{tmp_dir}/test.db")
        accession_number = storage.store_worklist_item(worklist_item)
        storage.update_status(accession_number, "IN PROGRESS", mpps_instance_uid)

        ae = AE(ae_title="MODALITY_SCU")
        ae.add_requested_context(ModalityPerformedProcedureStep)

        assoc = ae.associate("localhost", 4243, ae_title="SCREENING_MWL")

        mpps_ds = Dataset()
        mpps_ds.SOPClassUID = ModalityPerformedProcedureStep
        mpps_ds.PerformedProcedureStepStatus = "COMPLETED"
        now = datetime.datetime.now()
        mpps_ds.PerformedProcedureStepStartDate = now.strftime("%Y%m%d")
        mpps_ds.PerformedProcedureStepStartTime = now.strftime("%H%M%S")

        response = assoc.send_n_set(mpps_ds, ModalityPerformedProcedureStep, mpps_instance_uid)

        assert response[0].Status == SUCCESS

        updated_item = storage.get_worklist_item_by_mpps_instance_uid(mpps_instance_uid)

        assert updated_item is not None
        assert updated_item.mpps_instance_uid == mpps_instance_uid
        assert updated_item.status == "COMPLETED"
        assert updated_item.accession_number == accession_number
