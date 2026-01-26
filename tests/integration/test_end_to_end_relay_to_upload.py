"""
End-to-end integration test

This test verifies the complete flow from receiving a worklist item via Azure Relay
through to uploading the DICOM image to the Manage service.
"""

import json
from unittest.mock import Mock, patch

import pytest
from dicom_helpers import generate_random_dicom_file, send_dicom_file_to_server
from pydicom import Dataset
from pynetdicom import AE
from pynetdicom.sop_class import ModalityWorklistInformationFind

from relay_listener import RelayListener
from server import MWLServer, PACSServer
from services.dicom import PENDING, SUCCESS
from services.dicom.dicom_uploader import DICOMUploader
from services.dicom.upload_processor import UploadProcessor
from services.storage import MWLStorage, PACSStorage

TEST_ACCESSION_NUMBER = "ACC-E2E-12345"  # gitleaks:allow
TEST_PATIENT_ID = "9991234567"  # gitleaks:allow
TEST_ACTION_ID = "action-e2e-test-001"  # gitleaks:allow


@pytest.mark.integration
class TestEndToEndRelayToUpload:
    """
    End-to-end test covering the complete flow:

    1. Relay message received with worklist item
    2. Worklist item stored in MWL database
    3. C-FIND returns the scheduled worklist item
    4. C-STORE receives and validates DICOM image
    5. Upload processor sends image to Manage API with correct action_id
    """

    @pytest.fixture
    def mwl_storage(self, tmp_dir):
        return MWLStorage(f"{tmp_dir}/worklist.db")

    @pytest.fixture
    def pacs_storage(self, tmp_dir):
        return PACSStorage(f"{tmp_dir}/pacs.db", tmp_dir)

    @pytest.fixture
    def relay_payload(self):
        """Relay message payload that creates a worklist item."""
        return {
            "action_id": TEST_ACTION_ID,
            "action_type": "worklist.create_item",
            "parameters": {
                "worklist_item": {
                    "participant": {
                        "nhs_number": TEST_PATIENT_ID,
                        "name": "TEST^PATIENT",
                        "birth_date": "19850315",
                        "sex": "F",
                    },
                    "scheduled": {
                        "date": "20240620",
                        "time": "103000",
                    },
                    "procedure": {
                        "modality": "MG",
                        "study_description": "SCREENING MAMMOGRAPHY",
                    },
                    "accession_number": TEST_ACCESSION_NUMBER,
                }
            },
        }

    @pytest.fixture
    def mwl_server(self, mwl_storage):
        """MWL server using the shared storage."""
        server = MWLServer.__new__(MWLServer)
        server.ae_title = "MWL_SCP"
        server.port = 4243
        server.storage = mwl_storage
        server.ae = None
        server.block = False
        return server

    @pytest.fixture
    def pacs_server(self, pacs_storage):
        """PACS server using the shared storage."""
        server = PACSServer.__new__(PACSServer)
        server.ae_title = "SCREENING_PACS"
        server.port = 4244
        server.storage = pacs_storage
        server.ae = None
        server.block = False
        return server

    @pytest.mark.asyncio
    async def test_full_flow_relay_to_upload(
        self,
        mwl_storage,
        pacs_storage,
        mwl_server,
        pacs_server,
        relay_payload,
        fake_relay,
    ):
        """
        Complete end-to-end test of the screening gateway flow.

        This test verifies that:
        1. A relay message creates a worklist item
        2. The worklist item can be queried via C-FIND
        3. A DICOM image sent via C-STORE is validated and stored
        4. The upload processor sends the image with the correct action_id
        """

        # ===== STEP 1: Receive relay message and create worklist item =====
        listener = RelayListener(mwl_storage)
        relay_message = json.dumps({"accept": {"address": "wss://accept-url"}})

        with fake_relay(relay_message, json.dumps(relay_payload)) as ws_client:
            await listener.listen()

        # Verify worklist item was created
        ws_client.send.assert_called_once()
        response = json.loads(ws_client.send.call_args[0][0])
        assert response["status"] == "created"
        assert response["action_id"] == TEST_ACTION_ID

        worklist_items = mwl_storage.find_worklist_items()
        assert len(worklist_items) == 1
        assert worklist_items[0].accession_number == TEST_ACCESSION_NUMBER
        assert worklist_items[0].patient_id == TEST_PATIENT_ID

        # Update status to SCHEDULED so it appears in C-FIND results
        mwl_storage.update_status(TEST_ACCESSION_NUMBER, "SCHEDULED")

        # ===== STEP 2: Query worklist via C-FIND =====
        mwl_server.start()
        try:
            ae = AE(ae_title="TEST_MODALITY")
            ae.add_requested_context(ModalityWorklistInformationFind)
            assoc = ae.associate("127.0.0.1", 4243, ae_title="MWL_SCP")

            assert assoc.is_established, "Failed to establish C-FIND association"

            query = Dataset()
            query.PatientID = TEST_PATIENT_ID

            responses = list(assoc.send_c_find(query, query_model=ModalityWorklistInformationFind))
            assoc.release()

            # Should have 1 pending result + 1 success status
            assert len(responses) == 2
            status, ds = responses[0]
            assert status.Status == PENDING
            assert ds.PatientID == TEST_PATIENT_ID
            assert ds.AccessionNumber == TEST_ACCESSION_NUMBER

            status, ds = responses[1]
            assert status.Status == SUCCESS
        finally:
            mwl_server.stop()

        # ===== STEP 3: Send DICOM image via C-STORE =====
        pacs_server.start()
        try:
            # Generate a DICOM file with matching accession number
            dicom_file = generate_random_dicom_file(modality_type="MG")

            # Modify the file to use our test accession number
            import pydicom

            ds = pydicom.dcmread(dicom_file)
            ds.AccessionNumber = TEST_ACCESSION_NUMBER
            ds.PatientID = TEST_PATIENT_ID
            ds.save_as(dicom_file)

            # Send to PACS server
            success = send_dicom_file_to_server(
                dicom_file,
                "127.0.0.1",
                4244,
                "SCREENING_PACS",
                ae_title="TEST_MODALITY",
            )
            assert success, "C-STORE failed"

            # Clean up temp file
            import os

            os.remove(dicom_file)
        finally:
            pacs_server.stop()

        # Verify image was stored
        instance = pacs_storage.get_instance_by_accession(TEST_ACCESSION_NUMBER)
        assert instance is not None, "DICOM instance not found in storage"
        assert instance["accession_number"] == TEST_ACCESSION_NUMBER
        assert instance["patient_id"] == TEST_PATIENT_ID
        assert instance["upload_status"] == "PENDING"

        stored_sop_instance_uid = instance["sop_instance_uid"]

        # ===== STEP 4: Upload to Manage API =====
        mock_response = Mock()
        mock_response.status_code = 201

        with patch("services.dicom.dicom_uploader.requests.post") as mock_post:
            mock_post.return_value = mock_response

            uploader = DICOMUploader(api_endpoint="http://test-manage-api/upload")
            processor = UploadProcessor(
                pacs_storage=pacs_storage,
                mwl_storage=mwl_storage,
                uploader=uploader,
                max_retries=3,
            )

            processed = processor.process_batch(limit=10)
            assert processed == 1

            # Verify the upload was called with correct parameters
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args

            # Verify X-Source-Message-ID header contains the action_id from relay
            headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
            assert headers.get("X-Source-Message-ID") == TEST_ACTION_ID

            # Verify the file was included
            files = call_kwargs.kwargs.get("files", call_kwargs[1].get("files", {}))
            assert "file" in files
            filename, _ = files["file"]
            assert stored_sop_instance_uid in filename

        # Verify upload status was updated
        instance = pacs_storage.get_instance(stored_sop_instance_uid)
        assert instance["upload_status"] == "COMPLETE"
