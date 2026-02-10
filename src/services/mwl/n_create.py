import logging

from pydicom.dataset import Dataset
from pynetdicom.events import Event
from pynetdicom.sop_class import ModalityPerformedProcedureStep  # pyright: ignore[reportAttributeAccessIssue]

from services.dicom import DUPLICATE_SOP_INSTANCE, INVALID_ATTRIBUTE, MISSING_ATTRIBUTE, PROCESSING_FAILURE, SUCCESS
from services.mwl import MWLStatus
from services.storage import MWLStorage

logger = logging.getLogger(__name__)


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
            status = getattr(attr_list, "PerformedProcedureStepStatus", None)

            if not status:
                logger.warning("MPPS N-CREATE: Missing PerformedProcedureStepStatus in request")
                return MISSING_ATTRIBUTE, None

            if status.upper() != MWLStatus.IN_PROGRESS.value:
                logger.warning("MPPS N-CREATE: Invalid PerformedProcedureStepStatus value: %s", status)
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

            logger.info("MPPS N-CREATE: Started procedure for Accession Number: %s", accession_number)

            if not accession_number:
                logger.warning("MPPS N-CREATE: Missing Accession Number in ScheduledStepAttributesSequence")
                return MISSING_ATTRIBUTE, None

            source_message_id = self.storage.update_status(
                accession_number, MWLStatus.IN_PROGRESS.value, ds.SOPInstanceUID
            )
            if source_message_id:
                logger.info("Worklist item updated: %s -> %s", accession_number, MWLStatus.IN_PROGRESS.value)
            else:
                logger.warning("Could not find accession %s in database", accession_number)

        except Exception as e:
            logger.error("Error in handle_create: %s", str(e), exc_info=True)
            return PROCESSING_FAILURE, None

        # Success - return the created dataset
        logger.info("MPPS N-CREATE successful, returning dataset")
        return SUCCESS, ds
