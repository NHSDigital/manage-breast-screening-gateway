"""
DICOM upload listener service

Background service that polls the PACS database for stored DICOM images
and uploads them to the Manage Breast Screening HTTP API endpoint.
"""

import logging
import time

from services.dicom.upload_processor import UploadProcessor

logger = logging.getLogger(__name__)


class UploadListener:
    def __init__(
        self,
        processor: UploadProcessor,
        poll_interval: float = 2.0,
        batch_size: int = 10,
    ):
        """
        Initialize the upload listener.

        Args:
            processor: UploadProcessor instance for handling uploads
            poll_interval: Base interval between polling cycles in seconds
            batch_size: Maximum number of uploads to process per cycle
        """
        self.processor = processor
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self._running = False

    def start(self):
        logger.info("Upload listener started")
        self._running = True

        while self._running:
            try:
                self.processor.process_batch(limit=self.batch_size)

                # Add backoff delay to poll interval when experiencing failures
                sleep_time = self.poll_interval + self.processor.backoff_delay
                time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Error in upload listener: {e}", exc_info=True)
                time.sleep(self.poll_interval)

        logger.info("Upload listener stopped")

    def stop(self):
        logger.info("Stopping upload listener...")
        self._running = False
