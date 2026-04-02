import logging
import time
from datetime import datetime

from croniter import croniter

logger = logging.getLogger(__name__)


class MWLResetScheduler:
    def __init__(self, mwl_storage, backup_dir: str, schedule: str = "0 2 * * *"):
        """
        Args:
            mwl_storage: MWLStorage instance
            backup_dir: Directory to write backups to
            schedule: Cron expression for reset schedule in UTC (default: "0 2 * * *" — daily at 02:00)
        """
        self.mwl_storage = mwl_storage
        self.backup_dir = backup_dir
        self.schedule = schedule

    def run(self) -> None:
        logger.info(f"MWL reset scheduler started, schedule: '{self.schedule}' UTC")
        while True:
            next_reset = self._next_reset_datetime()
            delay = (next_reset - datetime.utcnow()).total_seconds()
            logger.info(f"Next MWL reset scheduled for {next_reset.isoformat()} UTC ({delay:.0f}s)")
            time.sleep(delay)
            self._backup_and_reset()

    def _next_reset_datetime(self) -> datetime:
        return croniter(self.schedule, datetime.utcnow()).get_next(datetime)

    def _backup_and_reset(self) -> None:
        logger.info("Starting MWL backup and reset")
        try:
            backup_path = self.mwl_storage.backup(self.backup_dir)
            logger.info(f"Backup complete: {backup_path}")
        except Exception as e:
            logger.error(f"MWL backup failed: {e}", exc_info=True)

        try:
            count = self.mwl_storage.clear()
            logger.info(f"MWL reset complete: {count} items deleted")
        except Exception as e:
            logger.error(f"MWL clear failed: {e}", exc_info=True)
