from unittest.mock import MagicMock, patch

import pytest
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid
from pynetdicom.sop_class import ModalityPerformedProcedureStep  # pyright: ignore[reportAttributeAccessIssue]

from services.dicom import (
    INVALID_ATTRIBUTE,
    MISSING_ATTRIBUTE,
    PROCESSING_FAILURE,
    SUCCESS,
    UNKNOWN_SOP_INSTANCE,
)
from services.mwl.n_set import NSet


@patch(f"{NSet.__module__}.MWLStorage")
class TestNSet:
    @pytest.fixture
    def event(self):
        event = MagicMock()
        event.request = MagicMock()
        event.attribute_list = Dataset()
        return event

    @pytest.fixture
    def requested_sop_instance_uid(self):
        return generate_uid()

    def test_missing_status_returns_processing_failure(self, mock_storage, event):
        event.request.RequestedSOPInstanceUID = generate_uid()

        # No PerformedProcedureStepStatus set
        status, ds = NSet(mock_storage).call(event)

        assert status == MISSING_ATTRIBUTE
        assert ds is None

    def test_invalid_status_returns_invalid_attribute(self, mock_storage, event, requested_sop_instance_uid):
        event.request.RequestedSOPInstanceUID = requested_sop_instance_uid
        event.attribute_list.PerformedProcedureStepStatus = "INVALID_STATUS"

        status, ds = NSet(mock_storage).call(event)

        assert status == INVALID_ATTRIBUTE
        assert ds is None

    def test_unknown_sop_instance_returns_unknown(self, mock_storage, event, requested_sop_instance_uid):
        event.request.RequestedSOPInstanceUID = requested_sop_instance_uid
        event.attribute_list.PerformedProcedureStepStatus = "COMPLETED"

        mock_storage.get_worklist_item_by_mpps_instance_uid.return_value = None

        status, ds = NSet(mock_storage).call(event)

        assert status == UNKNOWN_SOP_INSTANCE
        assert ds is None
        mock_storage.get_worklist_item_by_mpps_instance_uid.assert_called_once_with(requested_sop_instance_uid)

    def test_database_update_failure_returns_processing_failure(self, mock_storage, event, requested_sop_instance_uid):
        event.request.RequestedSOPInstanceUID = requested_sop_instance_uid
        event.attribute_list.PerformedProcedureStepStatus = "COMPLETED"

        worklist_item = MagicMock()
        worklist_item.accession_number = "ACC123"
        mock_storage.get_worklist_item_by_mpps_instance_uid.return_value = worklist_item

        mock_storage.update_status.return_value = None

        status, ds = NSet(mock_storage).call(event)

        assert status == PROCESSING_FAILURE
        assert ds is None
        mock_storage.update_status.assert_called_once_with("ACC123", "COMPLETED")

    def test_successful_nset_returns_success_and_dataset(self, mock_storage, event, requested_sop_instance_uid):
        event.request.RequestedSOPInstanceUID = requested_sop_instance_uid
        event.attribute_list.PerformedProcedureStepStatus = "COMPLETED"

        worklist_item = MagicMock()
        worklist_item.accession_number = "ACC123"
        mock_storage.get_worklist_item_by_mpps_instance_uid.return_value = worklist_item

        mock_storage.update_status.return_value = 1001  # mock message id

        status, ds = NSet(mock_storage).call(event)

        assert status == SUCCESS
        assert isinstance(ds, Dataset)
        assert ds.SOPClassUID == ModalityPerformedProcedureStep
        assert ds.SOPInstanceUID == requested_sop_instance_uid
        assert ds.PerformedProcedureStepStatus == "COMPLETED"

        mock_storage.update_status.assert_called_once_with("ACC123", "COMPLETED")

    def test_exception_returns_processing_failure(self, mock_storage, event):
        event.request.RequestedSOPInstanceUID = generate_uid()
        event.attribute_list.PerformedProcedureStepStatus = "COMPLETED"

        mock_storage.get_worklist_item_by_mpps_instance_uid.side_effect = Exception("DB error")

        status, ds = NSet(mock_storage).call(event)

        assert status == PROCESSING_FAILURE
        assert ds is None
