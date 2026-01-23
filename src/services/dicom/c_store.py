import logging
from io import BytesIO

from pydicom import Dataset, dcmwrite
from pynetdicom.events import Event
from pynetdicom.sop_class import (
    DigitalMammographyXRayImageStorageForPresentation,  # type: ignore
    DigitalMammographyXRayImageStorageForProcessing,  # type: ignore
)

from services.dicom import FAILURE, SUCCESS
from services.dicom.image_compressor import ImageCompressor
from services.dicom.validator import DicomValidationError, DicomValidator
from services.storage import InstanceExistsError, PACSStorage

logger = logging.getLogger(__name__)


class CStore:
    VALID_SOP_CLASSES = [
        DigitalMammographyXRayImageStorageForPresentation,
        DigitalMammographyXRayImageStorageForProcessing,
    ]

    def __init__(
        self,
        storage: PACSStorage,
        compressor: ImageCompressor | None = None,
        validator: DicomValidator | None = None,
    ):
        self.storage = storage
        self.compressor = compressor or ImageCompressor()
        self.validator = validator or DicomValidator()

    def call(self, event: Event) -> int:
        try:
            ds = event.dataset
            ds.file_meta = event.file_meta

            if ds.file_meta.MediaStorageSOPClassUID not in self.VALID_SOP_CLASSES:
                logger.error(f"Invalid SOP Class UID: {ds.file_meta.MediaStorageSOPClassUID}")
                return FAILURE

            sop_instance_uid = ds.get("SOPInstanceUID", "")
            if not sop_instance_uid:
                logger.error("Missing SOPInstanceUID")
                return FAILURE

            patient_id = ds.get("PatientID")
            if not patient_id:
                logger.error("Missing PatientID")
                return FAILURE

            accession_number = ds.get("AccessionNumber", "")
            patient_name = str(ds.get("PatientName", ""))

            # Validate dataset before compression
            try:
                self.validator.validate_dataset(ds)
                self.validator.validate_pixel_data(ds)
            except DicomValidationError as e:
                logger.error(f"DICOM validation failed: {e}")
                return FAILURE

            # Compress dataset before storing
            compressed_ds = self.compressor.compress(ds)

            # Serialize and validate output
            dicom_bytes = self.dataset_to_bytes(compressed_ds)
            try:
                self.validator.validate_bytes(dicom_bytes)
            except DicomValidationError as e:
                logger.error(f"Serialized DICOM invalid: {e}")
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
