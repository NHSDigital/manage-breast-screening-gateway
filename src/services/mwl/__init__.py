"""Modality Worklist (MWL) services for DICOM worklist management."""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class InvalidStatusTransitionError(Exception):
    """Raised when a requested status transition is not permitted."""

    pass


class MWLStatus(Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN PROGRESS"
    COMPLETED = "COMPLETED"
    DISCONTINUED = "DISCONTINUED"


class MWLStatusManager:
    _TRANSITIONS = {
        MWLStatus.IN_PROGRESS: MWLStatus.SCHEDULED,
        MWLStatus.COMPLETED: MWLStatus.IN_PROGRESS,
        MWLStatus.DISCONTINUED: MWLStatus.IN_PROGRESS,
    }

    @staticmethod
    def transition_for(status: str) -> tuple[MWLStatus, MWLStatus]:
        """
        Get the previous and next status for a given MWL status.

        Raises:
            InvalidStatusTransitionError: If the transition is not permitted
        """
        try:
            current_status = MWLStatus(status)
            previous_status = MWLStatusManager._TRANSITIONS[current_status]
            logger.info(f"Transitioning from {previous_status.value} to {current_status.value}")
            return previous_status, current_status
        except KeyError, ValueError:
            logger.error(f"Invalid status transition attempted for '{status}'")
            raise InvalidStatusTransitionError(f"Cannot transition to '{status}'")
