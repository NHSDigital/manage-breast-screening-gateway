from unittest.mock import MagicMock

import pytest
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid

from services.dicom import (
    DUPLICATE_SOP_INSTANCE,
    INVALID_ATTRIBUTE,
    MISSING_ATTRIBUTE,
    PROCESSING_FAILURE,
    SUCCESS,
)
from services.mwl.n_create import NCreate


class TestNCreate:
    @pytest.fixture
    def sop_instance_uid(self):
        return generate_uid()

    @pytest.fixture
    def storage(self):
        storage = MagicMock()
        storage.mpps_instance_exists.return_value = False
        storage.update_status.return_value = "source-msg-id"
        return storage

    @pytest.fixture
    def event(self, sop_instance_uid):
        event = MagicMock()

        # Mock request
        request = MagicMock()
        request.AffectedSOPInstanceUID = sop_instance_uid
        event.request = request

        # Mock attribute list (acts like a Dataset)
        attr_list = Dataset()
        attr_list.PerformedProcedureStepStatus = "IN PROGRESS"
        attr_list.Modality = "CT"

        # Scheduled Step Attributes
        sps = Dataset()
        sps.AccessionNumber = "ACC123"
        sps.StudyInstanceUID = generate_uid()

        attr_list.ScheduledStepAttributesSequence = [sps]

        event.attribute_list = attr_list
        return event

    def test_ncreate_success(self, storage, event, sop_instance_uid):
        status, ds = NCreate(storage).call(event)

        assert status == SUCCESS
        assert ds is not None
        assert ds.SOPInstanceUID == sop_instance_uid
        assert ds.PerformedProcedureStepStatus == "IN PROGRESS"

        storage.mpps_instance_exists.assert_called_once_with(sop_instance_uid)
        storage.update_status.assert_called_once_with("ACC123", "IN PROGRESS", sop_instance_uid)

    def test_ncreate_missing_sop_instance_uid(self, storage, event):
        event.request.AffectedSOPInstanceUID = None

        status, ds = NCreate(storage).call(event)

        assert status == INVALID_ATTRIBUTE
        assert ds is None

    def test_ncreate_duplicate_sop_instance(self, storage, event):
        storage.mpps_instance_exists.return_value = True

        status, ds = NCreate(storage).call(event)

        assert status == DUPLICATE_SOP_INSTANCE
        assert ds is None

    def test_ncreate_missing_pps_status(self, storage, event):
        del event.attribute_list.PerformedProcedureStepStatus

        status, ds = NCreate(storage).call(event)

        assert status == MISSING_ATTRIBUTE
        assert ds is None

    def test_ncreate_invalid_pps_status(self, storage, event):
        event.attribute_list.PerformedProcedureStepStatus = "COMPLETED"

        status, ds = NCreate(storage).call(event)

        assert status == INVALID_ATTRIBUTE
        assert ds is None

    def test_ncreate_missing_scheduled_step_sequence(self, storage, event):
        del event.attribute_list.ScheduledStepAttributesSequence

        status, ds = NCreate(storage).call(event)

        assert status == MISSING_ATTRIBUTE
        assert ds is None

    def test_ncreate_processing_failure(self, storage, event):
        storage.mpps_instance_exists.side_effect = Exception("Nooooo!")

        status, ds = NCreate(storage).call(event)

        assert status == PROCESSING_FAILURE
        assert ds is None

    def test_ncreate_missing_accession_number(self, storage, event):
        del event.attribute_list.ScheduledStepAttributesSequence[0].AccessionNumber

        status, ds = NCreate(storage).call(event)

        assert status == MISSING_ATTRIBUTE
        assert ds is None
