import logging
from io import BytesIO

from pydicom import Dataset, dcmwrite
from pydicom.filebase import DicomFileLike
from pynetdicom.events import Event

from services.storage import InstanceExistsError, PACSStorage

logger = logging.getLogger(__name__)

SUCCESS = 0x0000
FAILURE = 0xC000


class CStore:
    def __init__(self, storage: PACSStorage):
        self.storage = storage

    def call(self, event: Event) -> int:
        try:
            ds = event.dataset
            ds.file_meta = event.file_meta

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

            self.storage.store_instance(
                sop_instance_uid,
                self.dataset_to_bytes(ds),
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
