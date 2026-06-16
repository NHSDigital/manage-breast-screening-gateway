"""Entry point for DICOM upload listener service."""

import os

from dotenv import load_dotenv

from services.dicom.dicom_uploader import DICOMUploader
from services.dicom.upload_listener import UploadListener
from services.dicom.upload_processor import UploadProcessor
from services.storage import MWLStorage, PACSStorage
from telemetry import configure_logging, configure_telemetry

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
    logger = configure_logging("Gateway-Upload")

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

    logger.info("=" * 60)
    logger.info("Starting DICOM upload listener service")
    logger.info("=" * 60)
    logger.info(f"PACS DB: {pacs_storage.db_path}")
    logger.info(f"Worklist DB: {mwl_storage.db_path}")
    logger.info(f"Storage: {pacs_storage.storage_root}")
    logger.info(f"Poll interval: {poll_interval}s")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Max retries: {max_retries}")
    logger.info(f"API endpoint: {uploader.api_endpoint}")
    logger.info("=" * 60)

    configure_telemetry(service_name="upload-listener")

    try:
        listener.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        listener.stop()


if __name__ == "__main__":
    main()
