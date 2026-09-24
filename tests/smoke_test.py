import logging
import json
import os
import subprocess

import pydicom

from dotenv import load_dotenv
from integration.dicom_helpers import generate_random_dicom_file, send_dicom_file_to_server
from pydicom import Dataset
from pynetdicom import AE
from pynetdicom.sop_class import ModalityWorklistInformationFind
from relay_listener import RelayURI
from services.dicom import PENDING
from services.storage import PACSStorage

from websockets.sync.client import connect


logger = logging.getLogger(__name__)

load_dotenv()  # Load environment variables from .env file


TEST_ACCESSION_NUMBER = "ACC-SMOKE-12345"  # gitleaks:allow
TEST_PATIENT_ID = "9991234567"  # gitleaks:allow

os.environ["MWL_HOST"] = "0.0.0.0"
os.environ["PACS_HOST"] = "0.0.0.0"

def pacs_db_path():
    if os.getenv("DOCKER_GATEWAY") == "true":
        docker_info = subprocess.run(["docker", "volume", "inspect", "manage-breast-screening-gateway_pacs-db"], capture_output=True, text=True)
        docker_info_json = json.loads(docker_info.stdout)
        return docker_info_json[0]["Mountpoint"] + "/pacs.db"
    else:
        return os.environ.get("PACS_DB_PATH", "/var/lib/pacs/pacs.db")

# This smoke test is designed to verify the end-to-end functionality
# of the Relay Listener, MWL and PACS services on a deployed,
# Managed Identity secured Gateway deployed to Azure.


# 1. Connect to Relay and send a worklist item payload
def test_send_worklist_item_over_relay():
    payload = {
        "action_id": "action-12345",
        "action_type": "worklist.create_item",
        "parameters": {
            "worklist_item": {
                "participant": {
                    "nhs_number": TEST_PATIENT_ID,
                    "name": "SMITH^JANE",
                    "birth_date": "19900202",
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

    try:
        # We are connecting to a Relay Listener, so we need to use the "connect" action instead of "listen".
        url = RelayURI().connection_url().replace("sb-hc-action=listen", "sb-hc-action=connect")
        logger.info("Connecting to Relay at %s", url)
        with connect(url, compression=None, open_timeout=30) as conn:
            conn.send(json.dumps(payload))

            response = conn.recv(timeout=30)
            logger.info("Relay response: %s", response)
    except TimeoutError:
        logger.exception("Timed out communicating with relay")
    except Exception as e:
        logger.exception("Error communicating with relay")


# 2. Connect to MWL and perform a C-FIND to retrieve the worklist item
def test_c_find_worklist_item():
    ae = AE(ae_title="SMOKE_TEST_AET")
    ae.add_requested_context(ModalityWorklistInformationFind)

    logger.info(
        "Associating with MWL server %s at %s:%s",
        os.environ["MWL_AET"],
        os.environ["MWL_HOST"],
        os.environ["MWL_PORT"]
    )

    assoc = ae.associate(os.environ["MWL_HOST"], int(os.environ["MWL_PORT"]), ae_title=os.environ["MWL_AET"])
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

# 3. Connect to PACS and perform a C-STORE to send a DICOM image
def test_c_store_dicom_image():
    dicom_file = generate_random_dicom_file(TEST_ACCESSION_NUMBER)

    ds = pydicom.dcmread(dicom_file)
    ds.AccessionNumber = TEST_ACCESSION_NUMBER
    ds.PatientID = TEST_PATIENT_ID
    ds.save_as(dicom_file)

    success = send_dicom_file_to_server(
        dicom_file,
        os.environ["PACS_HOST"],
        int(os.environ["PACS_PORT"]),
        os.environ["PACS_AET"],
        ae_title="SMOKE_TEST_AE",
    )
    assert success, "C-STORE failed"

def test_image_stored_in_pacs():
    storage = PACSStorage(pacs_db_path(), os.environ["PACS_STORAGE_PATH"])
    stored_image = storage.get_image_by_accession_number(TEST_ACCESSION_NUMBER)
    assert stored_image is not None, "Stored image not found in PACS"
    assert stored_image.PatientID == TEST_PATIENT_ID, "Stored image PatientID does not match"
    assert stored_image.AccessionNumber == TEST_ACCESSION_NUMBER, "Stored image AccessionNumber does not match"
    assert stored_image.filepath is not None, "Stored image filepath is None"

    assert stored_image.uploaded_at is not None, "Stored image uploaded_at is None"
    # We expect a FAILED upload as the smoke test action id won't match anything in Rubie
    # or Rubie won't be available to receive the upload.
    assert stored_image.upload_status == "FAILED", "Stored image upload_status is not FAILED, no upload attempt was made"


def main():
    test_send_worklist_item_over_relay()
    test_c_find_worklist_item()
    test_c_store_dicom_image()
    test_image_stored_in_pacs()


if __name__ == "__main__":
    main()
