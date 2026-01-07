"""
C-FIND Handler for Modality Worklist queries.

Handles DICOM C-FIND requests from modalities querying the worklist.
"""

import logging
import sqlite3
from typing import Iterator, Tuple

from pydicom import Dataset
from pynetdicom import evt

from services.dicom import FAILURE, PENDING, SUCCESS
from services.storage import WorklistStorage

logger = logging.getLogger(__name__)


class CFindHandler:
    """Handler for C-FIND worklist queries."""

    def __init__(self, storage: WorklistStorage):
        self.storage = storage

    def call(self, event: evt.Event) -> Iterator[Tuple[int, Dataset | None]]:
        """
        Handle C-FIND request.

        Args:
            event: pynetdicom Event containing the C-FIND request

        Yields:
            Tuple of (status_code, dataset) for each matching worklist item.
            Dataset is None for final success/failure responses.
        """
        identifier = event.identifier
        requestor_aet = event.assoc.requestor.ae_title

        logger.info(f"C-FIND request from {requestor_aet}")

        query_modality = self._get_query_value(identifier, "ScheduledProcedureStepSequence", "Modality")
        query_date = self._get_query_value(
            identifier, "ScheduledProcedureStepSequence", "ScheduledProcedureStepStartDate"
        )
        query_patient_id = identifier.get("PatientID", "")

        logger.debug(f"Query parameters: modality={query_modality}, date={query_date}, patient_id={query_patient_id}")

        try:
            items = self.storage.find_worklist_items(
                modality=query_modality if query_modality else None,
                scheduled_date=query_date if query_date else None,
                patient_id=query_patient_id if query_patient_id else None,
                status="SCHEDULED",
            )

            logger.info(f"Found {len(items)} matching worklist items")

            for item in items:
                response_ds = self._build_worklist_response(item)
                yield PENDING, response_ds

            yield SUCCESS, None

        except Exception as e:
            logger.error(f"Error processing C-FIND request: {e}", exc_info=True)
            yield FAILURE, None

    def _get_query_value(self, ds: Dataset, sequence_tag: str, item_tag: str) -> str:
        try:
            sequence = ds.get(sequence_tag, [])
            if sequence and len(sequence) > 0:
                return str(sequence[0].get(item_tag, ""))
        except AttributeError, IndexError:
            pass
        return ""

    def _build_worklist_response(self, item: sqlite3.Row) -> Dataset:
        ds = Dataset()
        sps_item = Dataset()

        # Patient demographics
        ds.PatientID = item["patient_id"]
        ds.PatientName = item["patient_name"]
        ds.PatientBirthDate = item["patient_birth_date"]
        if "patient_sex" in item.keys():
            ds.PatientSex = item["patient_sex"]

        # Study information
        ds.AccessionNumber = item["accession_number"]
        if "study_instance_uid" in item.keys():
            ds.StudyInstanceUID = item["study_instance_uid"]

        if "study_description" in item.keys():
            ds.StudyDescription = item["study_description"]
            sps_item.ScheduledProcedureStepDescription = ds.StudyDescription

        if "procedure_code" in item.keys():
            ds.RequestedProcedureID = item["procedure_code"]
            sps_item.ScheduledProcedureStepID = ds.RequestedProcedureID

        # Scheduled Procedure Step Sequence
        sps_item.ScheduledProcedureStepStartDate = item["scheduled_date"]
        sps_item.ScheduledProcedureStepStartTime = item["scheduled_time"]
        sps_item.Modality = item["modality"]

        ds.ScheduledProcedureStepSequence = [sps_item]

        logger.debug(f"Built worklist response for accession {item['accession_number']}")

        return ds
