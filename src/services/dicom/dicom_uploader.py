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
        api_endpoint_url = api_endpoint_url + "/" + action_id

        files = {
            "file": (f"{sop_instance_uid}.dcm", dicom_stream),
        }

        try:
            logger.info("Uploading %s to %s", sop_instance_uid, api_endpoint_url)

            response = requests.put(
                api_endpoint_url,
                files=files,
                timeout=self.timeout,
                verify=self.verify_ssl,
                headers=auth_headers(),
            )

            if response.status_code == 201:
                logger.info("Successfully uploaded %s (status: %s)", sop_instance_uid, response.status_code)
                return True
            else:
                logger.error(
                    "Upload failed for %s: status %s, body: %s", sop_instance_uid, response.status_code, response.text
                )
                return False

        except requests.exceptions.Timeout:
            logger.error("Upload timeout for %s after %s", sop_instance_uid, self.timeout)
            return False
        except requests.exceptions.RequestException:
            logger.exception("Upload error for %s", sop_instance_uid)
            return False
