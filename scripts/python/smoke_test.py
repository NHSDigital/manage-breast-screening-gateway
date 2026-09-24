import datetime
import logging
import os
import random
import time

import numpy as np
from dotenv import load_dotenv
from PIL import Image
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from pynetdicom import AE
from pynetdicom.sop_class import (
    DigitalMammographyXRayImageStorageForPresentation,
    ModalityWorklistInformationFind,
)

from services.dicom import PENDING, SUCCESS
from services.mwl.create_worklist_item import CreateWorklistItem
from services.storage import MWLStorage, PACSStorage

logger = logging.getLogger(__name__)

load_dotenv()

if os.getenv("ENVIRONMENT", "").lower() == "prod":
    raise Exception("Smoke tests are not intended to be run in production environments.")

seed = random.randint(1000000, 9999999)
SAMPLE_IMAGES_PATH = os.getenv("SAMPLE_IMAGES_PATH", "sample_images")
TEST_ACCESSION_NUMBER = f"SMOKE-{seed}"  # gitleaks:allow
TEST_PATIENT_ID = f"999{seed}"  # gitleaks:allow
TEST_PATIENT_NAME = f"TEST^{seed}"  # gitleaks:allow
TEST_PATIENT_BIRTH_DATE = "19900101"  # gitleaks:allow
TEST_SCHEDULED_DATE = datetime.date.today().strftime("%Y%m%d")
TEST_SCHEDULED_TIME = datetime.datetime.now().strftime("%H%M%S")
TEST_STUDY_ID = f"STUDY{seed}"  # gitleaks:allow


# This smoke test is designed to verify the end-to-end functionality
# of the Relay Listener, MWL and PACS services on a deployed,
# Managed Identity secured Gateway deployed to Azure.


def generate_dicom_dataset():
    img_path = f"{SAMPLE_IMAGES_PATH}/LCC.jpg"
    img = Image.open(img_path).convert("L")
    columns, rows = img.size
    pixel_array = np.array(img, dtype=np.uint8)
    pixel_bytes = pixel_array.tobytes()
    if len(pixel_bytes) % 2 != 0:
        pixel_bytes += b"\x00"

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = DigitalMammographyXRayImageStorageForPresentation
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.ImplementationClassUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = Dataset()
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.PatientName = TEST_PATIENT_NAME
    ds.PatientID = TEST_PATIENT_ID
    ds.PatientBirthDate = TEST_PATIENT_BIRTH_DATE
    ds.PatientSex = "F"
    ds.StudyDate = TEST_SCHEDULED_DATE
    ds.StudyTime = TEST_SCHEDULED_TIME
    ds.StudyInstanceUID = generate_uid()
    ds.StudyID = TEST_STUDY_ID
    ds.AccessionNumber = TEST_ACCESSION_NUMBER
    ds.SeriesInstanceUID = generate_uid()
    ds.SeriesNumber = 1
    ds.InstanceNumber = 1
    ds.Modality = "MG"
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = rows
    ds.Columns = columns
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = pixel_bytes
    ds.ImageLaterality = "L"
    ds.ViewPosition = "CC"
    ds.file_meta = file_meta

    return ds


def test_create_worklist_item():
    payload = {
        "action_id": "action-12345",
        "action_type": "worklist.create_item",
        "parameters": {
            "worklist_item": {
                "participant": {
                    "nhs_number": TEST_PATIENT_ID,
                    "name": TEST_PATIENT_NAME,
                    "birth_date": TEST_PATIENT_BIRTH_DATE,
                    "sex": "F",
                },
                "scheduled": {
                    "date": "20240615",
                    "time": "101500",
                },
                "procedure": {
                    "modality": "MG",
                    "study_description": "MAMMOGRAPHY",
                },
                "accession_number": TEST_ACCESSION_NUMBER,
            }
        },
    }

    response = CreateWorklistItem(MWLStorage(os.environ["MWL_DB_PATH"])).call(payload)
    assert response == {"action_id": "action-12345", "status": "created"}


def test_c_find_worklist_item():
    mwl_host = os.getenv("MWL_HOST", "127.0.0.1")
    mwl_port = int(os.getenv("MWL_PORT", "4243"))
    ae = AE(ae_title="SMOKE_TEST_AET")
    ae.add_requested_context(ModalityWorklistInformationFind)

    logger.info("Associating with MWL server %s at %s:%s", os.environ["MWL_AET"], mwl_host, mwl_port)

    assoc = ae.associate(mwl_host, mwl_port, ae_title=os.environ["MWL_AET"])
    assert assoc.is_established, "Failed to establish C-FIND association"

    query = Dataset()
    query.PatientID = TEST_PATIENT_ID

    responses = list(
        assoc.send_c_find(
            query,
            query_model=ModalityWorklistInformationFind,
        )
    )
    assoc.release()

    assert len(responses) == 2, "Unexpected number of C-FIND responses"

    status, ds = responses[0]
    assert status.Status == PENDING, "C-FIND response status is not PENDING"
    assert ds.PatientID == TEST_PATIENT_ID, "C-FIND response PatientID does not match"


def test_c_store_dicom_image():
    pacs_host = os.getenv("PACS_HOST", "127.0.0.1")
    pacs_port = int(os.getenv("PACS_PORT", "4244"))
    ae = AE(ae_title="SMOKE_TEST_AET")
    ae.add_requested_context(DigitalMammographyXRayImageStorageForPresentation)
    pacs_assoc = ae.associate(pacs_host, pacs_port, ae_title=os.environ["PACS_AET"])

    assert pacs_assoc.is_established, "Failed to establish C-STORE association"

    ds = generate_dicom_dataset()
    response = pacs_assoc.send_c_store(ds)
    assert response.Status == SUCCESS, f"C-STORE failed with status: 0x{response.Status:04X}"


def test_image_stored_in_pacs():
    storage = PACSStorage(os.environ["PACS_DB_PATH"], os.environ["PACS_STORAGE_PATH"])
    stored_image = storage.get_instance_by_accession(TEST_ACCESSION_NUMBER)
    assert stored_image["patient_id"] == TEST_PATIENT_ID, "Stored image PatientID does not match"
    assert stored_image["accession_number"] == TEST_ACCESSION_NUMBER, "Stored image AccessionNumber does not match"
    assert stored_image["storage_path"] is not None, "Stored image storage_path is None"


def test_upload_attempted_for_stored_image():
    storage = PACSStorage(os.environ["PACS_DB_PATH"], os.environ["PACS_STORAGE_PATH"])
    max_wait_time = 10
    upload_attempted = False
    for _ in range(max_wait_time):
        stored_image = storage.get_instance_by_accession(TEST_ACCESSION_NUMBER)
        # We expect a FAILED upload as the smoke test action id won't match anything in Rubie
        # or Rubie won't be available to receive the upload.
        if stored_image["upload_status"] == "FAILED":
            upload_attempted = True
            break
        time.sleep(1)

    assert upload_attempted, f"No upload attempt detected within {max_wait_time} seconds"
