import asyncio
import logging

from modality_emulator import ModalityEmulator

from ..storage import MWLStorage
from .create_worklist_item import CreateWorklistItem

logger = logging.getLogger(__name__)


class CreateTestWorklistItem(CreateWorklistItem):
    def __init__(self, storage: MWLStorage):
        super().__init__(storage)
        self._background_tasks: set[asyncio.Task] = set()

    def call(self, payload: dict):
        result = super().call(payload)
        status = result.get("status")

        parameters = payload.get("parameters", {})
        worklist_item = parameters.get("worklist_item", {})
        accession_number = worklist_item.get("accession_number")
        patient_name = worklist_item.get("participant", {}).get("name")

        if status == "error":
            return result

        if not patient_name:
            message = "No patient name provided for ModalityEmulator test item processing"
            logger.warning(message)
            return {"status": "error", "message": message}

        if status == "exists":
            return result

        if payload.get("parameters", {}).get("emulate_modality", True):
            self.process_with_modality_emulator(
                patient_name=patient_name,
                accession_number=accession_number,
            )

        return result

    def process_with_modality_emulator(
        self,
        patient_name: str,
        accession_number: str,
    ):
        """Process worklist items with ModalityEmulator, then clean up."""

        def _run_emulator():
            try:
                ModalityEmulator(self.storage).process_worklist_items(
                    patient_name=patient_name,
                )
            except Exception:
                logger.exception("Modality emulator processing failed")
                return

            try:
                self.storage.delete_worklist_item(accession_number)
            except Exception:
                logger.exception("Failed to delete worklist item %s", accession_number)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Called outside an event loop (e.g. unit tests)
            _run_emulator()
        else:
            task = loop.create_task(asyncio.to_thread(_run_emulator))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
