import logging

from pydicom.dataset import Dataset
from pynetdicom.events import Event
from pynetdicom.sop_class import ModalityPerformedProcedureStep  # pyright: ignore[reportAttributeAccessIssue]

from services.dicom import DUPLICATE_SOP_INSTANCE, INVALID_ATTRIBUTE, MISSING_ATTRIBUTE, PROCESSING_FAILURE, SUCCESS
from services.storage import MWLStorage

logger = logging.getLogger(__name__)

UNKNOWN = "UNKNOWN"


class NCreate:
    def __init__(self, storage: MWLStorage):
        self.storage = storage

    def call(self, event: Event) -> tuple[int, Dataset | None]:
        """Handle N-CREATE request for MPPS (start of procedure)."""
        ds = Dataset()
        try:
            req = event.request

            affected_sop_instance_uid = getattr(req, "AffectedSOPInstanceUID", None)

            if affected_sop_instance_uid is None:
                return INVALID_ATTRIBUTE, None

            if self.storage.mpps_instance_exists(affected_sop_instance_uid):
                return DUPLICATE_SOP_INSTANCE, None

            attr_list = event.attribute_list

            if "PerformedProcedureStepStatus" not in attr_list:
                return MISSING_ATTRIBUTE, None

            if attr_list.PerformedProcedureStepStatus.upper() != "IN PROGRESS":
                return INVALID_ATTRIBUTE, None

            ds.SOPClassUID = ModalityPerformedProcedureStep
            ds.SOPInstanceUID = affected_sop_instance_uid
            ds.update(attr_list)

            scheduled_step_sequence = getattr(attr_list, "ScheduledStepAttributesSequence", [])
            if len(scheduled_step_sequence) == 0:
                logger.warning("MPPS N-CREATE: Missing ScheduledStepAttributesSequence in request")
                return MISSING_ATTRIBUTE, None

            sps = attr_list.ScheduledStepAttributesSequence[0]
            accession_number = sps.get("AccessionNumber")

            logger.info("MPPS N-CREATE: Started procedure for Accession Number: %w", accession_number)

            if not accession_number:
                logger.warning("MPPS N-CREATE: Missing Accession Number in ScheduledStepAttributesSequence")
                return MISSING_ATTRIBUTE, None

            source_message_id = self.storage.update_status(accession_number, "IN_PROGRESS", ds.SOPInstanceUID)
            if source_message_id:
                logger.info(f"Worklist item updated: {accession_number} -> IN_PROGRESS")
            else:
                logger.warning(f"Could not find accession {accession_number} in database")

        except Exception as e:
            logger.error(f"Error in handle_create: {str(e)}", exc_info=True)
            return PROCESSING_FAILURE, None

        # Success - return the created dataset
        logger.info("MPPS N-CREATE successful, returning dataset")
        return SUCCESS, ds
