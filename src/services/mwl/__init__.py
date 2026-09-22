"""Modality Worklist (MWL) services for DICOM worklist management."""

from enum import Enum


class InvalidStatusTransitionError(Exception):
    """Raised when a requested status transition is not permitted."""

    pass


class MWLStatus(Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN PROGRESS"
    COMPLETED = "COMPLETED"
    DISCONTINUED = "DISCONTINUED"


class MWLStatusManager:
    REVERSED_TRANSITIONS = {
        MWLStatus.IN_PROGRESS: [MWLStatus.SCHEDULED],
        MWLStatus.COMPLETED: [MWLStatus.IN_PROGRESS],
        MWLStatus.DISCONTINUED: [MWLStatus.SCHEDULED, MWLStatus.IN_PROGRESS],
    }

    @staticmethod
    def transition_for(status: str) -> tuple[list[str], str]:
        """
        Get the current and next status for a given MWL status.

        Raises:
            InvalidStatusTransitionError: If the transition is not permitted
        """
        try:
            next_status = MWLStatus(status)
            current_statuses = MWLStatusManager.REVERSED_TRANSITIONS[next_status]
            current_status_values = [s.value for s in current_statuses]
            return current_status_values, next_status.value
        except KeyError:
            raise InvalidStatusTransitionError(f"Cannot transition to '{status}'")
        except ValueError:
            raise InvalidStatusTransitionError(f"Invalid MWL status '{status}'")
