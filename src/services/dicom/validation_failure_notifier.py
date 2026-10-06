"""Notifier for DICOM C-STORE validation failures.

Reports validation failures to the Manage Breast Screening HTTP API.
"""

import logging

import requests

import config
from services.dicom.cloud_api_auth import auth_headers

logger = logging.getLogger(__name__)


class ValidationFailureNotifier:
    def __init__(self, api_endpoint: str | None = None, timeout: int = 30, verify_ssl: bool = True):
        self.api_endpoint = api_endpoint or config.cloud_api_endpoint()
        self.timeout = timeout
        self.verify_ssl = verify_ssl

    def notify(self, source_message_id: str, error: str) -> bool:
        try:
            logger.info(f"Reporting validation failure for action {source_message_id}")

            response = requests.patch(
                f"{self.api_endpoint}/{source_message_id}/failure",
                json={"error": error},
                timeout=self.timeout,
                verify=self.verify_ssl,
                headers=auth_headers(),
            )

            if response.status_code == 200:
                logger.info(f"Validation failure reported for action {source_message_id}")
                return True
            else:
                logger.error(
                    f"Failed to report validation failure for {source_message_id}: "
                    f"status {response.status_code}, body: {response.text}"
                )
                return False

        except requests.exceptions.Timeout:
            logger.error(f"Timeout reporting validation failure for {source_message_id} after {self.timeout}s")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error reporting validation failure for {source_message_id}: {e}", exc_info=True)
            return False
