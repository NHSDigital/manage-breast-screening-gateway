import pytest

from services.mwl import (
    InvalidStatusTransitionError,
    MWLStatus,
    MWLStatusManager,
)


@pytest.mark.parametrize(
    ("status", "expected_current_statuses", "expected_next_status"),
    [
        (MWLStatus.IN_PROGRESS, ["SCHEDULED"], "IN PROGRESS"),
        (MWLStatus.COMPLETED, ["IN PROGRESS"], "COMPLETED"),
        (
            MWLStatus.DISCONTINUED,
            ["SCHEDULED", "IN PROGRESS"],
            "DISCONTINUED",
        ),
    ],
)
def test_transition_for_returns_expected_transitions_for_supported_statuses(
    status: MWLStatus,
    expected_current_statuses: list[str],
    expected_next_status: str,
) -> None:
    current_statuses, next_status = MWLStatusManager.transition_for(status.value)

    assert current_statuses == expected_current_statuses
    assert next_status == expected_next_status


def test_transition_for_raises_for_scheduled_status() -> None:
    with pytest.raises(InvalidStatusTransitionError, match="Cannot transition to"):
        MWLStatusManager.transition_for(MWLStatus.SCHEDULED.value)


@pytest.mark.parametrize("status", ["invalid", "", "DONE"])
def test_transition_for_raises_for_invalid_status_values(status: str) -> None:
    with pytest.raises(InvalidStatusTransitionError, match="Invalid MWL status"):
        MWLStatusManager.transition_for(status)
