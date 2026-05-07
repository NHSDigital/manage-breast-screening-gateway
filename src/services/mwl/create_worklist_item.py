import logging

from models import WorklistItem
from services.storage import MWLStorage, WorklistItemExistsError

logger = logging.getLogger(__name__)


class CreateWorklistItem:
    def __init__(self, storage: MWLStorage):
        self.storage = storage

    def call(self, payload: dict):
        try:
            action_id = payload.get("action_id")
            if not action_id:
                raise ValueError("Missing action_id in payload")

            params = payload.get("parameters", {})

            item = params.get("worklist_item", {})
            accession_number = item.get("accession_number")
            participant = item.get("participant", {})
            scheduled = item.get("scheduled", {})
            procedure = item.get("procedure", {})

            self.storage.store_worklist_item(
                WorklistItem(
                    accession_number=accession_number,
                    patient_id=participant.get("nhs_number"),
                    patient_name=participant.get("name"),
                    patient_birth_date=participant.get("birth_date"),
                    patient_sex=participant.get("sex", ""),
                    scheduled_date=scheduled.get("date"),
                    scheduled_time=scheduled.get("time"),
                    modality=procedure.get("modality"),
                    study_description=procedure.get("study_description", ""),
                    source_message_id=action_id,
                )
            )
            logger.info(f"Created worklist item: {accession_number}")
            return {"status": "created", "action_id": action_id}
        except WorklistItemExistsError:
            logger.info(f"Worklist item exists: accession_number={accession_number}, action_id={action_id!r}")
            return {"status": "exists", "action_id": action_id}
        except Exception as e:
            logger.error(f"Failed to create worklist item: {e}")
            return {"status": "error", "action_id": action_id, "error": str(e)}
