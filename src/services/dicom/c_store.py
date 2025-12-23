from pynetdicom.events import Event
from pydicom.dataset import Dataset
from io import BytesIO
from services.storage import InstanceExistsError, PACSStorage

import logging

logger = logging.getLogger(__name__)

SUCCESS = 0x0000
FAILURE = 0xC000


class CStore:
    def __init__(self, storage: PACSStorage):
        self.storage = storage

    def call(self, nhs_number: str, event: Event):
        try:
            ds = event.dataset
            ds.file_meta = event.file_meta

            sop_instance_uid = ds.get("SOPInstanceUID", "")
            if not sop_instance_uid:
                logger.error("Missing SOP Instance UID")
                return FAILURE

            accession_number = ds.get("AccessionNumber", "")

            self.storage.store_instance(
                sop_instance_uid,
                self.ds_file_data(ds),
                {
                    "accession_number": accession_number,
                    "nhs_number": nhs_number
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

    def ds_file_data(self, ds: Dataset) -> bytes:
        # Serialize dataset to bytes
        buffer = BytesIO()
        ds.save_as(buffer, write_like_original=False)
        return buffer.getvalue()
