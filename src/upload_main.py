"""Entry point for DICOM upload listener service."""

import logging
import os

from dotenv import load_dotenv

from services.dicom.dicom_uploader import DICOMUploader
from services.dicom.upload_listener import UploadListener
from services.dicom.upload_processor import UploadProcessor
from services.storage import MWLStorage, PACSStorage

load_dotenv()


def main():
    """
    Main entry point for upload listener service.

    Environment variables:
    CLOUD_API_ENDPOINT: URL of the cloud API endpoint to upload to (default: http://localhost:8000/api/dicom/upload)
    CLOUD_API_KEY: API key for authenticating with the cloud API (default: none)
    MAX_UPLOAD_RETRIES: Maximum number of upload retries before giving up (default: 3)
    MWL_DB_PATH: Path to the MWL SQLite database file (default: /var/lib/pacs/worklist.db)
    PACS_DB_PATH: Path to the PACS SQLite database file (default: /var/lib/pacs/pacs.db)
    PACS_STORAGE_PATH: Path to the directory where DICOM files are stored (default: /var/lib/pacs/storage)
    UPLOAD_POLL_INTERVAL: Time in seconds between polling for new uploads (default: 2)
    UPLOAD_BATCH_SIZE: Number of pending uploads to process in each batch (default: 10)
    """
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )

    poll_interval = float(os.getenv("UPLOAD_POLL_INTERVAL", "2"))
    batch_size = int(os.getenv("UPLOAD_BATCH_SIZE", "10"))
    max_retries = int(os.getenv("MAX_UPLOAD_RETRIES", "3"))

    pacs_storage = PACSStorage(
        os.getenv("PACS_DB_PATH", "/var/lib/pacs/pacs.db"), os.getenv("PACS_STORAGE_PATH", "/var/lib/pacs/storage")
    )
    mwl_storage = MWLStorage(os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db"))
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
