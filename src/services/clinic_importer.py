import json
import logging
import os

import requests
from azure.identity import ManagedIdentityCredential

from environment import Environment
from services.mwl.create_worklist_item import CreateWorklistItem
from services.storage import MWLStorage

logger = logging.getLogger(__name__)


class ClinicImporter:
    def __init__(self, storage: MWLStorage, options):
        self.storage = storage
        self.options = options

    def import_data(self):
        if self.is_api_import():
            self.import_from_api()
        elif self.is_file_import():
            self.import_from_file()
        else:
            raise ValueError("Invalid import options specified for clinic import.")

    def is_api_import(self):
        return self.options.get("source") == "api" and self.options.get("api_url") is not None

    def is_file_import(self):
        return self.options.get("source") == "file" and self.options.get("file_path") is not None

    def import_from_api(self):
        logger.info("Importing clinic data from API: %s", self.options.get("api_url"))

        response = requests.get(
            self.options.get("api_url"),
            timeout=self.options.get("timeout", 30),
            verify=self.options.get("verify_ssl", True),
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        clinic_data = response.json()
        worklist_items = clinic_data.get("worklist_items", [])

        logger.info("Found %s worklist items in API response.", len(worklist_items))

        for item in worklist_items:
            CreateWorklistItem(self.storage).call(item)

        logger.info("Clinic data import completed.")

    def import_from_file(self):
        file_path = self.options.get("file_path")
        try:
            logger.info("Importing clinic data from file: %s", file_path)
            worklist_items = []
            with open(file_path, "r") as file:
                raw_data = file.read()
                clinic_data = json.loads(raw_data)
                worklist_items = clinic_data.get("worklist_items", [])

            logger.info("Found %s worklist items in import file.", len(worklist_items))

            for item in worklist_items:
                CreateWorklistItem(self.storage).call(item)

            logger.info("Clinic data import completed.")
        except ValueError:
            logger.exception("Failed to parse JSON from import file: %s", file_path)
        except FileNotFoundError:
            logger.exception("Import file not found: %s", file_path)
        finally:
            os.rename(file_path, f"{file_path}.processed")

    @property
    def access_token(self) -> str | None:
        resource = os.getenv("CLOUD_API_RESOURCE", "")
        if resource or Environment().production:
            return ManagedIdentityCredential().get_token(resource).token
        else:
            return os.getenv("CLOUD_API_TOKEN", "")
