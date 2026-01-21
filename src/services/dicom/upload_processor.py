"""
DICOM upload processor

Handles the logic for uploading DICOM instances to the cloud API,
including retry handling and status tracking.
"""

import logging

from services.dicom.dicom_uploader import DICOMUploader
from services.storage import MWLStorage, PACSStorage

logger = logging.getLogger(__name__)


class UploadProcessor:
    def __init__(
        self,
        pacs_storage: PACSStorage,
        mwl_storage: MWLStorage,
        uploader: DICOMUploader,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        backoff_multiplier: float = 2.0,
    ):
        self.pacs_storage = pacs_storage
        self.mwl_storage = mwl_storage
        self.uploader = uploader
        self.max_retries = max_retries
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._backoff_multiplier = backoff_multiplier
        self._current_backoff = 0.0

    def process_batch(self, limit: int = 10) -> int:
        pending = self.pacs_storage.get_pending_uploads(limit=limit, max_retries=self.max_retries)

        if not pending:
            self._reset_backoff()
            return 0

        logger.info(f"Found {len(pending)} images pending upload")

        successes = 0
        for instance in pending:
            if self.upload_instance(instance):
                successes += 1

        failures = len(pending) - successes

        if failures > 0:
            self._increase_backoff()
            logger.info(
                f"Batch complete: {successes}/{len(pending)} succeeded, backoff now {self._current_backoff:.1f}s"
            )
        else:
            self._reset_backoff()
            logger.info(f"Batch complete: all {len(pending)} uploads succeeded")

        return len(pending)

    @property
    def backoff_delay(self) -> float:
        return self._current_backoff

    def _reset_backoff(self) -> None:
        if self._current_backoff > 0:
            logger.debug(f"Resetting backoff from {self._current_backoff:.1f}s to 0")
        self._current_backoff = 0.0

    def _increase_backoff(self) -> None:
        if self._current_backoff == 0:
            self._current_backoff = self._initial_backoff
        else:
            self._current_backoff = min(
                self._current_backoff * self._backoff_multiplier,
                self._max_backoff,
            )
        logger.debug(f"Increased backoff to {self._current_backoff:.1f}s")

    def upload_instance(self, instance: dict) -> bool:
        sop_instance_uid = instance["sop_instance_uid"]
        storage_path = instance["storage_path"]
        accession_number = instance.get("accession_number")
        attempt_count = instance.get("upload_attempt_count", 0)

        logger.info(f"Processing upload {sop_instance_uid} (attempt {attempt_count + 1}/{self.max_retries})")

        try:
            self.pacs_storage.mark_upload_started(sop_instance_uid)

            dicom_path = self.pacs_storage.storage_root / storage_path
            if not dicom_path.exists():
                error = f"DICOM file not found: {dicom_path}"
                logger.error(error)
                self._mark_failed(sop_instance_uid, error, attempt_count + 1)
                return False

            dicom_bytes = dicom_path.read_bytes()
            logger.debug(f"Read {len(dicom_bytes)} bytes from {dicom_path}")

            action_id = self.mwl_storage.get_source_message_id(accession_number) if accession_number else None

            if self.uploader.upload_dicom(sop_instance_uid, dicom_bytes, action_id):
                self.pacs_storage.mark_upload_complete(sop_instance_uid)
                logger.info(f"Successfully uploaded {sop_instance_uid}")
                return True
            else:
                error = "Upload returned failure status"
                self._mark_failed(sop_instance_uid, error, attempt_count + 1)
                return False

        except Exception as e:
            error = f"Unexpected error: {str(e)}"
            logger.error(f"Error uploading {sop_instance_uid}: {e}", exc_info=True)
            self._mark_failed(sop_instance_uid, error, attempt_count + 1)
            return False

    def _mark_failed(self, sop_instance_uid: str, error: str, attempt_count: int) -> None:
        permanent = attempt_count >= self.max_retries
        self.pacs_storage.mark_upload_failed(sop_instance_uid, error, permanent=permanent)

        if permanent:
            logger.error(f"Upload permanently failed for {sop_instance_uid} after {attempt_count} attempts: {error}")
        else:
            logger.warning(
                f"Upload failed for {sop_instance_uid} (attempt {attempt_count}/{self.max_retries}): {error}"
            )
