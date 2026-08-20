from dataclasses import dataclass, field
from typing import Optional

from services.mwl import MWLStatus


@dataclass
class WorklistItem:
    accession_number: str = field(
        doc="A departmental Information System generated number that identifies the Imaging Service Request.",
    )
    clinic_id: str = field(doc="Identifier for the clinic or department where the procedure is scheduled.")
    modality: str = field(doc="Code for type of equipment that will perform the procedure.")
    patient_birth_date: str = field(doc="Date of Birth of the Patient.")
    patient_id: str = field(doc="Patient NHS Number", hash=True)
    patient_name: str = field(doc="Name of the patient. Lastname^Firstname.")
    scheduled_date: str = field(doc="Date the procedure is scheduled for.")
    scheduled_time: str = field(doc="Time the procedure is scheduled for.")
    status: str = field(doc="Status of the worklist item", default=MWLStatus.SCHEDULED.value)

    source_message_id: Optional[str] = field(
        default=None, doc="Message ID from system which created this worklist item", hash=True
    )
    study_instance_uid: Optional[str] = field(default=None, doc="Instance UID for the study", hash=True)
    procedure_code: Optional[str] = field(default=None, doc="Code that identifies the requested procedure.")
    patient_sex: Optional[str] = field(default=None, doc="Sex of the patient.")
    study_description: Optional[str] = field(default=None, doc="Description of the study.")
    mpps_instance_uid: Optional[str] = field(
        default=None, doc="Modality Performed Procedure Step (MPPS) instance UID if available."
    )

    patient_age: Optional[str] = field(default=None, doc="Age of the patient at the time of scheduling.")
    patient_weight: Optional[str] = field(default=None, doc="Weight of the patient at the time of scheduling.")
    patient_address: Optional[str] = field(default=None, doc="Address of the patient.")
    patient_comments: Optional[str] = field(default=None, doc="Additional comments about the patient.")

    procedure_coding_scheme_designator: Optional[str] = field(
        default=None, doc="Coding scheme designator for the procedure code."
    )
    procedure_code_meaning: Optional[str] = field(default=None, doc="Code meaning for the procedure code.")

    reason_code_value: Optional[str] = field(default=None, doc="Code value for the reason for requested procedure.")
    reason_coding_scheme_designator: Optional[str] = field(
        default=None, doc="Coding scheme designator for the reason for requested procedure."
    )
    reason_code_meaning: Optional[str] = field(default=None, doc="Code meaning for the reason for requested procedure.")

    scheduled_performing_physician_name: Optional[str] = field(
        default=None, doc="Name of the scheduled performing physician."
    )
    scheduled_procedure_step_location: Optional[str] = field(
        default=None, doc="Location of the scheduled procedure step."
    )
    scheduled_station_aet: Optional[str] = field(default=None, doc="AE Title of the scheduled station.")
    scheduled_station_name: Optional[str] = field(default=None, doc="Name of the scheduled station.")
    scheduled_protocol_code_value: Optional[str] = field(default=None, doc="Code value for the scheduled protocol.")
    scheduled_protocol_coding_scheme_designator: Optional[str] = field(
        default=None, doc="Coding scheme designator for the scheduled protocol."
    )
    scheduled_protocol_code_meaning: Optional[str] = field(default=None, doc="Code meaning for the scheduled protocol.")
