import logging

from pydicom import Dataset
from pynetdicom.events import Event
from pynetdicom.sop_class import ModalityPerformedProcedureStep  # pyright: ignore[reportAttributeAccessIssue]

from services.dicom import INVALID_ATTRIBUTE, MISSING_ATTRIBUTE, PROCESSING_FAILURE, SUCCESS, UNKNOWN_SOP_INSTANCE
from services.mwl import MWLStatus
from services.storage import MWLStorage

logger = logging.getLogger(__name__)


class NSet:
    def __init__(self, storage: MWLStorage):
        self.storage = storage

    def call(self, event: Event) -> tuple[int, Dataset | None]:
        try:
            req = event.request
            requested_sop_instance_uid = getattr(req, "RequestedSOPInstanceUID", None)
            logger.info("MPPS N-SET: Received request for SOP Instance UID: %s", requested_sop_instance_uid)

            mod_list = event.attribute_list
            status = mod_list.get("PerformedProcedureStepStatus")
            if not status:
                logger.warning("MPPS N-SET: Missing PerformedProcedureStepStatus in request")
                return MISSING_ATTRIBUTE, None

            if status not in [MWLStatus.COMPLETED.value, MWLStatus.DISCONTINUED.value]:
                logger.warning("MPPS N-SET: Invalid PerformedProcedureStepStatus: %s", status)
                return INVALID_ATTRIBUTE, None

            worklist_item = self.storage.get_worklist_item_by_mpps_instance_uid(requested_sop_instance_uid)
            if not worklist_item:
                logger.warning(
                    "MPPS N-SET: No worklist item found for SOP Instance UID: %s", requested_sop_instance_uid
                )
                return UNKNOWN_SOP_INSTANCE, None

            accession_number = worklist_item.accession_number

            source_message_id = self.storage.update_status(accession_number, status)
            if source_message_id:
                logger.info("Database updated: %s -> %s", accession_number, status)

                ds = Dataset()
                ds.SOPClassUID = ModalityPerformedProcedureStep
                ds.SOPInstanceUID = requested_sop_instance_uid
                ds.update(mod_list)

                logger.info("MPPS N-SET successful")
                return SUCCESS, ds
            else:
                logger.warning("MPPS N-SET: Failed to update database with new status")
                return PROCESSING_FAILURE, None
        except Exception as e:
            logger.error("Error in handle_set: %s", str(e), exc_info=True)
            return PROCESSING_FAILURE, None
