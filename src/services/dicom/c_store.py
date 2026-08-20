import logging
from io import BytesIO

import config

import numpy as np

from PIL import Image as PILImage
from pydicom import Dataset, dcmwrite
from pynetdicom.events import Event

from services.dicom import FAILURE, SUCCESS
from services.dicom.image_compressor import ImageCompressor
from services.dicom.validation_failure_notifier import ValidationFailureNotifier
from services.dicom.validator import DicomValidationError, DicomValidator
from services.mwl import MWLStatus
from services.storage import InstanceExistsError, MWLStorage, PACSStorage

logger = logging.getLogger(__name__)


class CStore:
    def __init__(
        self,
        storage: PACSStorage,
        compressor: ImageCompressor | None = None,
        validator: DicomValidator | None = None,
        mwl_storage: MWLStorage | None = None,
        notifier: ValidationFailureNotifier | None = None,
    ):
        self.storage = storage
        self.compressor = compressor or ImageCompressor()
        self.validator = validator or DicomValidator()
        self.mwl_storage = mwl_storage
        self.notifier = notifier or ValidationFailureNotifier()

    def call(self, event: Event) -> int:
        try:
            ds = event.dataset
            ds.file_meta = event.file_meta

            sop_instance_uid = ds.get("SOPInstanceUID", "")
            accession_number = ds.get("AccessionNumber", "")
            patient_id = ds.get("PatientID")
            patient_name = str(ds.get("PatientName", ""))

            if not sop_instance_uid:
                logger.error("Missing SOPInstanceUID")
                self._notify_failure(accession_number, "Missing SOPInstanceUID")
                return FAILURE

            if not patient_id:
                logger.error("Missing PatientID")
                self._notify_failure(accession_number, "Missing PatientID")
                return FAILURE

            # Validate dataset before compression
            try:
                self.validator.validate_dataset(ds)
                self.validator.validate_pixel_data(ds)
            except DicomValidationError as e:
                logger.error(f"DICOM validation failed: {e}")
                self._notify_failure(accession_number, f"DICOM validation failed: {e}")
                return FAILURE

            # Compress dataset before storing
            compressed_ds = self.compressor.compress(ds)

            # Serialize and validate output
            dicom_bytes = self.dataset_to_bytes(compressed_ds)
            try:
                self.validator.validate_bytes(dicom_bytes)
            except DicomValidationError as e:
                logger.error(f"Serialized DICOM invalid: {e}")
                self._notify_failure(accession_number, f"Serialized DICOM invalid: {e}")
                return FAILURE

            self.storage.store_instance(
                sop_instance_uid,
                dicom_bytes,
                {
                    "accession_number": accession_number,
                    "patient_id": patient_id,
                    "patient_name": patient_name,
                },
                event.assoc.requestor.ae_title,
            )
            # TODO: Move to a utility module.
            if config.store_images():
                image_bytes = self.dataset_to_jpeg_bytes(sop_instance_uid, compressed_ds)
                laterality = getattr(ds, "ImageLaterality", "")
                view_position = getattr(ds, "ViewPosition", "")
                implant_present = "ID" if getattr(ds, "BreastImplantPresent", "") == "YES" else ""
                suffix = f"{laterality}{view_position}{implant_present}.jpg"
                self.storage.store_file(sop_instance_uid, image_bytes, suffix=suffix)

            self._mark_in_progress(accession_number)
            return SUCCESS

        except InstanceExistsError:
            # Instance already exists
            logger.warning(f"Instance already exists: {sop_instance_uid}")
            return SUCCESS

        except Exception as e:
            logger.error(e, exc_info=True)
            return FAILURE

    def dataset_to_bytes(self, ds: Dataset) -> bytes:
        with BytesIO() as buffer:
            # enforce_file_format=True ensures the 128-byte preamble and 'DICM' prefix are written
            dcmwrite(buffer, ds, enforce_file_format=True)
            buffer.seek(0)
            return buffer.read()

    def _mark_in_progress(self, accession_number: str) -> None:
        if not self.mwl_storage or not accession_number:
            return
        try:
            self.mwl_storage.update_status(accession_number, MWLStatus.IN_PROGRESS.value)
        except Exception as e:
            logger.error(f"Failed to mark worklist item in progress: {e}", exc_info=True)

    def _notify_failure(self, accession_number: str, error: str) -> None:
        if not self.mwl_storage or not self.notifier:
            return

        source_message_id = self.mwl_storage.get_source_message_id(accession_number)
        if not source_message_id:
            logger.warning(
                f"Cannot report validation failure: no worklist item found for accession {accession_number!r}"
            )
            return

        self.notifier.notify(source_message_id, error)

    # TODO: This should live in a utility module.
    def dataset_to_jpeg_bytes(self, sop_uid: str, ds: pydicom.Dataset) -> bytes:
        """Convert a DICOM dataset to a JPEG image and return it as bytes."""
        # Normalize pixel data to 0-255 and convert to uint8
        pixel_array = ds.pixel_array
        pixel_array = pixel_array.astype(np.float32)

        if getattr(ds, "PhotometricInterpretation", "") == "MONOCHROME1":
            pixel_array = np.max(pixel_array) - pixel_array

        pixel_array -= pixel_array.min()
        pixel_array /= pixel_array.max()
        pixel_array *= 255.0
        pixel_array = pixel_array.astype(np.uint8)
        image = PILImage.fromarray(pixel_array, mode="L")

        img_bytes = BytesIO()
        image.save(img_bytes, format="JPEG")
        img_bytes.seek(0)
        return img_bytes.getvalue()
