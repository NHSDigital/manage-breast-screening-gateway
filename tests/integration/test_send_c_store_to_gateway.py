import os
from pathlib import Path

import pytest
from dicom_helpers import send_random_dicom_series

from models import WorklistItem
from server import PACSServer
from services.storage import MWLStorage, PACSStorage


@pytest.mark.integration
class TestSendCStoreToGateway:
    @pytest.fixture(autouse=True)
    def with_pacs_server(self, tmp_dir):
        server = PACSServer(
            "SCREENING_PACS", 4244, tmp_dir, f"{tmp_dir}/test.db", block=False, mwl_db_path=f"{tmp_dir}/worklist.db"
        )
        server.start()

        yield

        server.stop()

    def test_send_dicom_series_to_gateway(self, tmp_dir):
        """Send DICOM series to gateway."""
        accession_numbers = [f"ACC{i:03d}" for i in range(1, 6)]
        storage = PACSStorage(f"{tmp_dir}/test.db", str(tmp_dir))
        mwl_storage = MWLStorage(f"{tmp_dir}/worklist.db")

        for accession_number in accession_numbers:
            mwl_storage.store_worklist_item(
                WorklistItem(
                    accession_number=accession_number,
                    modality="MG",
                    patient_birth_date="19800101",
                    patient_id=f"ID{accession_number[-3:]}",
                    patient_name=f"RANDOM^{accession_number[-3:]}",
                    scheduled_date="20240101",
                    scheduled_time="090000",
                    source_message_id=f"action-uuid-{accession_number[-3:]}",
                )
            )

        send_random_dicom_series(
            accession_numbers,
            os.getenv("PACS_SERVER_ADDRESS", "0.0.0.0"),
            os.getenv("PACS_SERVER_PORT", 4244),
            "SCREENING_PACS",
        )

        with storage._get_connection() as conn:
            cursor = conn.execute(
                """
                    SELECT  patient_id, patient_name,
                            accession_number, storage_path
                    FROM    stored_instances
                    WHERE   status = 'STORED'
                """
            )
            results = cursor.fetchall()

        assert len(results) == len(accession_numbers)

        for result in results:
            assert "ID" in result["patient_id"]
            assert "RANDOM^" in result["patient_name"]
            assert result["accession_number"] in accession_numbers
            assert Path(f"{tmp_dir}/{result['storage_path']}").is_file()
