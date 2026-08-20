import json
import os
from pathlib import Path
from zipfile import ZipFile
import config
from services.storage import MWLStorage, PACSStorage


class ClinicExporter:
    def __init__(self, mwl_storage: MWLStorage, pacs_storage: PACSStorage, clinic_id: str):
        self.mwl_storage = mwl_storage
        self.pacs_storage = pacs_storage
        self.clinic_id = clinic_id
        self.zip_file_path = Path(config.export_directory()) / f"clinic-export-{self.clinic_id}.zip"

    def export_archive(self):
        worklist_items = self.mwl_storage.find_worklist_items(clinic_id=self.clinic_id)

        if worklist_items is None:
            raise ValueError(f"No worklist items found for clinic_id: {self.clinic_id}")

        with ZipFile(self.zip_file_path, "w") as zip_file:
            for item in worklist_items:
                accession_number = item.accession_number
                zip_file.writestr(f"{accession_number}/item.json", json.dumps(item.__dict__, indent=4))

                study_instances = self.pacs_storage.get_instances_by_accession(accession_number)
                for instance in study_instances:
                    dicom_file_path = Path(self.pacs_storage.storage_root / instance["storage_path"])
                    if dicom_file_path.exists():
                        zip_file.write(str(dicom_file_path), arcname=f"{accession_number}/{instance['sop_instance_uid']}.dcm")
