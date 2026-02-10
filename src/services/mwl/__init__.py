"""Modality Worklist (MWL) services for DICOM worklist management."""

from enum import Enum


class MWLStatus(Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN PROGRESS"
    COMPLETED = "COMPLETED"
    DISCONTINUED = "DISCONTINUED"
