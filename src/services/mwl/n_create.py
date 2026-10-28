import logging

from pydicom.dataset import Dataset
from pynetdicom.events import Event
from pynetdicom.sop_class import ModalityPerformedProcedureStep  # pyright: ignore[reportAttributeAccessIssue]

from services.dicom import (
    DUPLICATE_SOP_INSTANCE,
    INVALID_ATTRIBUTE,
    MISSING_ATTRIBUTE,
    PROCESSING_FAILURE,
    SUCCESS,
)
from services.dicom.character_set import CharacterSet
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
            attr_list = getattr(event, "attribute_list", None)

            affected_sop_instance_uid = getattr(req, "AffectedSOPInstanceUID", None)

            if affected_sop_instance_uid is None:
                return INVALID_ATTRIBUTE, None

            if self.storage.mpps_instance_exists(affected_sop_instance_uid):
                return DUPLICATE_SOP_INSTANCE, None

            status = getattr(attr_list, "PerformedProcedureStepStatus", None) if attr_list is not None else None

            if not status:
                logger.warning("MPPS N-CREATE: Missing PerformedProcedureStepStatus in request")
                return MISSING_ATTRIBUTE, None

            if str(status).upper() != MWLStatus.IN_PROGRESS.value:
                logger.warning("MPPS N-CREATE: Invalid PerformedProcedureStepStatus value: %s", status)
                return INVALID_ATTRIBUTE, None

            if attr_list is not None:
                ds.update(attr_list)

            ds.SpecificCharacterSet = CharacterSet.resolve(attr_list)
            ds.SOPClassUID = ModalityPerformedProcedureStep
            ds.SOPInstanceUID = affected_sop_instance_uid

            scheduled_step_sequence = getattr(attr_list, "ScheduledStepAttributesSequence", [])
            if len(scheduled_step_sequence) == 0:
                logger.warning("MPPS N-CREATE: Missing ScheduledStepAttributesSequence in request")
                return MISSING_ATTRIBUTE, None

            sps = scheduled_step_sequence[0]
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

        except Exception:
            logger.exception("Error in handle_create")
            return PROCESSING_FAILURE, None

        # Success - return the created dataset
        logger.info("MPPS N-CREATE successful, returning dataset")
        return SUCCESS, ds
