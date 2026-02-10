"""Modality Worklist (MWL) services for DICOM worklist management."""

from enum import Enum

from services.mwl.c_find import CFindHandler

__all__ = ["CFindHandler"]


class MWLStatus(Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN PROGRESS"
    COMPLETED = "COMPLETED"
    DISCONTINUED = "DISCONTINUED"
