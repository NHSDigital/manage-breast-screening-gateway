import datetime
import logging
import os
import random
import time

import numpy as np
import pytest
from dotenv import load_dotenv
from PIL import Image
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from pynetdicom import AE
from pynetdicom.sop_class import (
    DigitalMammographyXRayImageStorageForPresentation,
    ModalityWorklistInformationFind,
)

from services.dicom import PENDING, SUCCESS, next_message_id
from services.mwl.create_worklist_item import CreateWorklistItem
from services.storage import MWLStorage, PACSStorage

logger = logging.getLogger(__name__)

load_dotenv()

seed = random.randint(1000000, 9999999)
SAMPLE_IMAGES_PATH = os.getenv("SAMPLE_IMAGES_PATH", "sample_images")
SMOKE_TEST_AET = "SMOKE_TEST_AET"
TEST_ACCESSION_NUMBER = f"SMOKE-{seed}"  # gitleaks:allow
# DicomUploader will skip uploads with action_id containing "SMOKE-"
# to avoid uploading test images to the Rubie API.
TEST_ACTION_ID = f"SMOKE-{seed}"  # gitleaks:allow
TEST_PATIENT_ID = f"999{seed}"  # gitleaks:allow
TEST_PATIENT_NAME = f"TEST^{seed}"  # gitleaks:allow
TEST_PATIENT_BIRTH_DATE = "19900101"  # gitleaks:allow
TEST_SCHEDULED_DATE = datetime.date.today().strftime("%Y%m%d")
TEST_SCHEDULED_TIME = datetime.datetime.now().strftime("%H%M%S")
TEST_STUDY_ID = f"STUDY{seed}"  # gitleaks:allow


@pytest.fixture(scope="module")
def mwl_storage():
    return MWLStorage(os.environ["MWL_DB_PATH"])


@pytest.fixture(scope="module")
def pacs_storage():
    return PACSStorage(os.environ["PACS_DB_PATH"], os.environ["PACS_STORAGE_PATH"])


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


def create_worklist_item(mwl_storage):
    payload = {
        "action_id": TEST_ACTION_ID,
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
                    "date": TEST_SCHEDULED_DATE,
                    "time": TEST_SCHEDULED_TIME,
                },
                "procedure": {
                    "modality": "MG",
                    "study_description": "MAMMOGRAPHY",
                },
                "accession_number": TEST_ACCESSION_NUMBER,
            }
        },
    }

    response = CreateWorklistItem(mwl_storage).call(payload)
    assert response == {"action_id": TEST_ACTION_ID, "status": "created"}


def c_find_worklist_item():
    mwl_host = os.getenv("MWL_HOST", "127.0.0.1")
    mwl_port = int(os.getenv("MWL_PORT", "4243"))
    ae = AE(ae_title=SMOKE_TEST_AET)
    ae.add_requested_context(ModalityWorklistInformationFind)

    logger.info("Associating with MWL server %s at %s:%s", os.environ["MWL_AET"], mwl_host, mwl_port)

    assoc = ae.associate(mwl_host, mwl_port, ae_title=os.environ["MWL_AET"])
    assert assoc.is_established, "Failed to establish C-FIND association"

    message_id = next_message_id()
    query = Dataset()
    query.MessageID = message_id
    query.PatientID = TEST_PATIENT_ID

    responses = list(
        assoc.send_c_find(
            query,
            query_model=ModalityWorklistInformationFind,
            msg_id=message_id,
        )
    )
    assoc.release()

    assert len(responses) == 2, "Unexpected number of C-FIND responses"

    status, ds = responses[0]
    assert status.Status == PENDING, "C-FIND response status is not PENDING"
    assert ds.PatientID == TEST_PATIENT_ID, "C-FIND response PatientID does not match"
    assert ds.MessageIDBeingRespondedTo == message_id, "C-FIND response does not echo MessageID"


def store_dicom_image():
    pacs_host = os.getenv("PACS_HOST", "127.0.0.1")
    pacs_port = int(os.getenv("PACS_PORT", "4244"))
    ae = AE(ae_title=SMOKE_TEST_AET)
    ae.add_requested_context(DigitalMammographyXRayImageStorageForPresentation)
    pacs_assoc = ae.associate(pacs_host, pacs_port, ae_title=os.environ["PACS_AET"])

    assert pacs_assoc.is_established, "Failed to establish C-STORE association"

    ds = generate_dicom_dataset()
    response = pacs_assoc.send_c_store(ds)
    assert response.Status == SUCCESS, f"C-STORE failed with status: 0x{response.Status:04X}"


def get_image_stored_in_pacs(pacs_storage):
    stored_image = pacs_storage.get_instance_by_accession(TEST_ACCESSION_NUMBER)
    assert stored_image["patient_id"] == TEST_PATIENT_ID, "Stored image PatientID does not match"
    assert stored_image["accession_number"] == TEST_ACCESSION_NUMBER, "Stored image AccessionNumber does not match"
    assert stored_image["storage_path"] is not None, "Stored image storage_path is None"


def get_status_of_stored_image(pacs_storage):
    max_wait_time = 30
    stored_image = pacs_storage.get_instance_by_accession(TEST_ACCESSION_NUMBER)

    for _ in range(max_wait_time):
        if stored_image["upload_status"] == "COMPLETE":
            break
        time.sleep(1)
        stored_image = pacs_storage.get_instance_by_accession(TEST_ACCESSION_NUMBER)
    else:
        pytest.fail(f"Stored image upload_status did not become COMPLETE within {max_wait_time} seconds")

    assert stored_image["upload_status"] == "COMPLETE", "Stored image upload_status is not COMPLETE"


@pytest.fixture
def delete_worklist_item(mwl_storage):
    try:
        yield
    finally:
        mwl_storage.delete_worklist_item(TEST_ACCESSION_NUMBER)


@pytest.fixture
def teardown(pacs_storage, delete_worklist_item):
    try:
        yield
    finally:
        stored_image = pacs_storage.get_instance_by_accession(TEST_ACCESSION_NUMBER)
        if stored_image is not None:
            pacs_storage.delete_instance(stored_image["sop_instance_uid"])


def test_gateway(mwl_storage, pacs_storage, teardown):
    create_worklist_item(mwl_storage)
    c_find_worklist_item()
    store_dicom_image()
    get_image_stored_in_pacs(pacs_storage)
    get_status_of_stored_image(pacs_storage)
