"""
C-FIND Handler for Modality Worklist queries.

Handles DICOM C-FIND requests from modalities querying the worklist.
"""

import logging
from typing import Iterator, Tuple

from pydicom import Dataset
from pynetdicom import evt

from models import WorklistItem
from services.dicom import FAILURE, PENDING, SUCCESS
from services.dicom.character_set import CharacterSet
from services.storage import MWLStorage

logger = logging.getLogger(__name__)


class CFind:
    """Handler for C-FIND worklist queries."""

    def __init__(self, storage: MWLStorage):
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

        character_set = CharacterSet.resolve(identifier)

        query_patient_id = identifier.get("PatientID")
        anonymised_patient_id = f"*******{query_patient_id[7:]}" if query_patient_id else "None"
        query_patient_name = identifier.get("PatientName")

        procedure_sequence = identifier.get("ScheduledProcedureStepSequence", [{}])
        query_modality = procedure_sequence[0].get("Modality")
        query_date = procedure_sequence[0].get("ScheduledProcedureStepStartDate")
        query_accession_number = identifier.get("AccessionNumber")
        query_time = procedure_sequence[0].get("ScheduledProcedureStepStartTime")

        logger.debug(
            "Query parameters: modality=%s, date=%s, patient_id=%s, patient_name=%s",
            query_modality,
            query_date,
            anonymised_patient_id,
            query_patient_name,
        )

        try:
            items = self.storage.find_worklist_items(
                accession_number=query_accession_number if query_accession_number else None,
                modality=query_modality if query_modality else None,
                scheduled_date=query_date if query_date else None,
                scheduled_time=query_time if query_time else None,
                patient_id=query_patient_id if query_patient_id else None,
                patient_name=str(query_patient_name) if query_patient_name else None,
            )

            logger.info("Found %s matching worklist items", len(items))

            for item in items:
                response_ds = self._build_worklist_response(item)
                response_ds.SpecificCharacterSet = character_set
                yield PENDING, response_ds

            yield SUCCESS, None

        except Exception as e:
            logger.error("Error processing C-FIND request: %s", e, exc_info=True)
            yield FAILURE, None

    def _build_worklist_response(self, item: WorklistItem) -> Dataset:
        ds = Dataset()
        sps_item = Dataset()

        # Patient demographics
        ds.PatientID = item.patient_id
        ds.PatientName = item.patient_name
        ds.PatientBirthDate = item.patient_birth_date
        ds.PatientSex = item.patient_sex
        ds.PatientAge = item.patient_age
        ds.PatientWeight = item.patient_weight
        ds.PatientAddress = item.patient_address
        ds.PatientComments = item.patient_comments

        # Study information
        ds.AccessionNumber = item.accession_number
        ds.StudyInstanceUID = item.study_instance_uid

        ds.StudyDescription = item.study_description
        sps_item.ScheduledProcedureStepDescription = ds.StudyDescription

        ds.RequestedProcedureID = item.procedure_code

        ds.RequestedProcedureCodeSequence = [Dataset()]
        ds.RequestedProcedureCodeSequence[0].CodeValue = item.procedure_code
        ds.RequestedProcedureCodeSequence[0].CodingSchemeDesignator = item.procedure_coding_scheme_designator
        ds.RequestedProcedureCodeSequence[0].CodeMeaning = item.procedure_code_meaning

        ds.ReasonForRequestedProcedureCodeSequence = [Dataset()]
        ds.ReasonForRequestedProcedureCodeSequence[0].CodeValue = item.reason_code_value
        ds.ReasonForRequestedProcedureCodeSequence[0].CodingSchemeDesignator = item.reason_coding_scheme_designator
        ds.ReasonForRequestedProcedureCodeSequence[0].CodeMeaning = item.reason_code_meaning

        sps_item.ScheduledProcedureStepID = ds.RequestedProcedureID

        # Scheduled Procedure Step Sequence
        sps_item.ScheduledProcedureStepStartDate = item.scheduled_date
        sps_item.ScheduledProcedureStepStartTime = item.scheduled_time
        sps_item.Modality = item.modality
        sps_item.ScheduledStationAETitle = item.scheduled_station_aet
        sps_item.ScheduledPerformingPhysicianName = item.scheduled_performing_physician_name
        sps_item.ScheduledStationName = item.scheduled_station_name
        sps_item.ScheduledProcedureStepLocation = item.scheduled_procedure_step_location
        sps_item.ScheduledProtocolCodeSequence = [Dataset()]
        sps_item.ScheduledProtocolCodeSequence[0].CodeValue = item.scheduled_protocol_code_value
        sps_item.ScheduledProtocolCodeSequence[
            0
        ].CodingSchemeDesignator = item.scheduled_protocol_coding_scheme_designator
        sps_item.ScheduledProtocolCodeSequence[0].CodeMeaning = item.scheduled_protocol_code_meaning

        ds.ScheduledProcedureStepSequence = [sps_item]

        logger.debug("Built worklist response for accession %s", item.accession_number)

        return ds
