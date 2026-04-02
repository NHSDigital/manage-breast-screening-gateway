from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from services.mwl.reset import MWLResetScheduler
from services.storage import MWLStorage


class TestMWLResetScheduler:
    @pytest.fixture
    def mock_storage(self):
        mock = Mock(spec=MWLStorage)
        mock.backup.return_value = "/backups/20240101-020000.worklist.db.backup"
        return mock

    @pytest.fixture
    def scheduler(self, mock_storage):
        return MWLResetScheduler(mock_storage, "/backups", schedule="0 2 * * *")

    def test_next_reset_datetime_is_in_the_future(self, scheduler):
        assert scheduler._next_reset_datetime() > datetime.utcnow()

    def test_next_reset_datetime_is_within_24_hours(self, scheduler):
        assert scheduler._next_reset_datetime() <= datetime.utcnow() + timedelta(hours=24)

    def test_next_reset_datetime_has_correct_time(self, scheduler):
        next_reset = scheduler._next_reset_datetime()
        assert next_reset.hour == 2
        assert next_reset.minute == 0
        assert next_reset.second == 0

    def test_next_reset_datetime_weekly_schedule(self, mock_storage):
        scheduler = MWLResetScheduler(mock_storage, "/backups", schedule="0 2 * * 1")  # Mondays at 02:00
        next_reset = scheduler._next_reset_datetime()
        assert next_reset > datetime.utcnow()
        assert next_reset <= datetime.utcnow() + timedelta(days=7)
        assert next_reset.weekday() == 0  # Monday

    def test_backup_and_reset_calls_backup_then_clear(self, scheduler, mock_storage):
        scheduler._backup_and_reset()

        mock_storage.backup.assert_called_once_with("/backups")
        mock_storage.clear.assert_called_once()

    def test_backup_failure_does_not_prevent_clear(self, mock_storage):
        mock_storage.backup.side_effect = Exception("disk full")
        scheduler = MWLResetScheduler(mock_storage, "/backups")

        scheduler._backup_and_reset()

        mock_storage.clear.assert_called_once()

    def test_clear_failure_is_caught(self, mock_storage):
        mock_storage.clear.side_effect = Exception("db locked")
        scheduler = MWLResetScheduler(mock_storage, "/backups")

        scheduler._backup_and_reset()  # should not raise
