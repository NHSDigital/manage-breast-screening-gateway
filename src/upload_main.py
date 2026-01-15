"""Entry point for DICOM upload listener service."""

import logging
import os

from services.dicom.dicom_uploader import DICOMUploader
from services.dicom.upload_listener import UploadListener
from services.dicom.upload_processor import UploadProcessor
from services.storage import MWLStorage, PACSStorage


def main():
    """Main entry point for upload listener service."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )

    poll_interval = float(os.getenv("UPLOAD_POLL_INTERVAL", "2"))
    batch_size = int(os.getenv("UPLOAD_BATCH_SIZE", "10"))
    max_retries = int(os.getenv("MAX_UPLOAD_RETRIES", "3"))

    pacs_storage = PACSStorage()
    mwl_storage = MWLStorage()
    uploader = DICOMUploader()

    processor = UploadProcessor(
        pacs_storage=pacs_storage,
        mwl_storage=mwl_storage,
        uploader=uploader,
        max_retries=max_retries,
    )

    listener = UploadListener(
        processor=processor,
        poll_interval=poll_interval,
        batch_size=batch_size,
    )

    logging.info("=" * 60)
    logging.info("Starting DICOM upload listener service")
    logging.info("=" * 60)
    logging.info(f"PACS DB: {pacs_storage.db_path}")
    logging.info(f"Worklist DB: {mwl_storage.db_path}")
    logging.info(f"Storage: {pacs_storage.storage_root}")
    logging.info(f"Poll interval: {poll_interval}s")
    logging.info(f"Batch size: {batch_size}")
    logging.info(f"Max retries: {max_retries}")
    logging.info(f"API endpoint: {uploader.api_endpoint}")
    logging.info("=" * 60)

    try:
        listener.start()
    except KeyboardInterrupt:
        logging.info("Received shutdown signal")
        listener.stop()


if __name__ == "__main__":
    main()
