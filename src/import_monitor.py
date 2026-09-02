import glob
import os
import time
import logging

import config
from services.clinic_importer import ClinicImporter
from services.storage import MWLStorage
from telemetry import configure_telemetry

logger = logging.getLogger(__name__)


class ImportMonitor:
    def __init__(self):
        self.import_directory = config.import_directory()
        os.makedirs(self.import_directory, exist_ok=True)
        self.poll_interval = config.import_poll_interval()
        self.storage = MWLStorage(db_path=config.mwl_db_path())
        self._running = False

    def start(self):
        logger.info("Starting import monitor for directory: %s", self.import_directory)

        if not os.path.exists(self.import_directory):
            logger.error("Import directory does not exist: %s", self.import_directory)
            return

        self._running = True

        while self._running:
            try:
                self.check_for_new_files()
                time.sleep(self.poll_interval)
            except Exception as e:
                logger.exception("Error in import monitor")
                time.sleep(self.poll_interval)

    def stop(self):
        logger.info("Stopping import monitor...")
        self._running = False

    def check_for_new_files(self):
        for filename in glob.glob(os.path.join(self.import_directory, "*.json")):
            logger.info("Import file detected: %s", filename)
            ClinicImporter(self.storage, {"source": "file", "file_path": filename}).import_data()


def main():
    configure_telemetry(service_name="import-monitor")
    monitor = ImportMonitor()

    try:
        monitor.start()
    except KeyboardInterrupt:
        monitor.stop()
    except Exception as e:
        logger.exception("Unexpected error in import monitor")
        monitor.stop()


if __name__ == "__main__":
    main()
