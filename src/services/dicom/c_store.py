import logging
from io import BytesIO

from pydicom import Dataset, dcmwrite
from pydicom.filebase import DicomFileLike
from pynetdicom.events import Event
from pynetdicom.sop_class import (
    DigitalMammographyXRayImageStorageForPresentation,  # type: ignore
    DigitalMammographyXRayImageStorageForProcessing,  # type: ignore
)

from services.dicom import FAILURE, SUCCESS
from services.dicom.image_compressor import ImageCompressor
from services.storage import InstanceExistsError, PACSStorage

logger = logging.getLogger(__name__)


class CStore:
    VALID_SOP_CLASSES = [
        DigitalMammographyXRayImageStorageForPresentation,
        DigitalMammographyXRayImageStorageForProcessing,
    ]

    def __init__(self, storage: PACSStorage, compressor: ImageCompressor | None = None):
        self.storage = storage
        self.compressor = compressor or ImageCompressor()

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

            # Compress dataset before storing
            compressed_ds = self.compressor.compress(ds)

            self.storage.store_instance(
                sop_instance_uid,
                self.dataset_to_bytes(compressed_ds),
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

    # https://pydicom.github.io/pydicom/stable/auto_examples/memory_dataset.html
    def dataset_to_bytes(self, ds: Dataset) -> bytes:
        with BytesIO() as buffer:
            memory_dataset = DicomFileLike(buffer)
            dcmwrite(memory_dataset, ds)
            memory_dataset.seek(0)
            return memory_dataset.read()
