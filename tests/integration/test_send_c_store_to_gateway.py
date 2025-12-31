import os
import threading
from pathlib import Path

import pytest
from dicom_helpers import send_random_dicom_series

from server import PACSServer
from services.storage import PACSStorage


class TestSendCStoreToGateway:
    @pytest.fixture(autouse=True)
    def with_pacs_server(self, tmp_dir):
        server = PACSServer("SCREENING_PACS", 4244, tmp_dir, f"{tmp_dir}/test.db")
        thread = threading.Thread(target=server.start)
        thread.start()

        yield

        server.stop()

    def test_send_dicom_series_to_gateway(self, tmp_dir):
        number_of_instances = 5
        storage = PACSStorage(f"{tmp_dir}/test.db", str(tmp_dir))
        send_random_dicom_series(
            number_of_instances,
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

        assert len(results) == number_of_instances

        for result in results:
            assert "ID" in result["patient_id"]
            assert "RANDOM^" in result["patient_name"]
            assert "ACC" in result["accession_number"]
            assert Path(f"{tmp_dir}/{result['storage_path']}").is_file()
