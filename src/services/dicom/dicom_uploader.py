"""
Cloud DICOM uploader

Uploads DICOM files to the Manage Breast Screening HTTP API endpoint.
"""

import io
import logging
from typing import Optional

import requests

import config
from services.dicom.cloud_api_auth import auth_headers

logger = logging.getLogger(__name__)


class DICOMUploader:
    def __init__(self, api_endpoint: str | None = None, timeout: int = 30, verify_ssl: bool = True):
        self.api_endpoint = api_endpoint or config.cloud_api_endpoint()
        self.timeout = timeout
        self.verify_ssl = verify_ssl

    def upload_dicom(
        self, sop_instance_uid: str, dicom_stream: io.BufferedReader, source_attributes: Optional[tuple]
    ) -> bool:
        action_id, base_url = source_attributes if source_attributes else (None, None)

        if not action_id:
            logger.error(f"No action_id for {sop_instance_uid}, upload will be rejected by server")
            return False

        api_endpoint_url = config.cloud_api_endpoint(base_url) if base_url else self.api_endpoint

        files = {
            "file": (f"{sop_instance_uid}.dcm", dicom_stream),
        }

        try:
            logger.info(f"Uploading {sop_instance_uid} to {self.api_endpoint}/{action_id}")

            response = requests.put(
                f"{api_endpoint_url}/{action_id}",
                files=files,
                timeout=self.timeout,
                verify=self.verify_ssl,
                headers=auth_headers(),
            )

            if response.status_code == 201:
                logger.info(f"Successfully uploaded {sop_instance_uid} (status: {response.status_code})")
                return True
            else:
                logger.error(
                    f"Upload failed for {sop_instance_uid}: status {response.status_code}, body: {response.text}"
                )
                return False

        except requests.exceptions.Timeout:
            logger.error(f"Upload timeout for {sop_instance_uid} after {self.timeout}s")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Upload error for {sop_instance_uid}: {e}", exc_info=True)
            return False
