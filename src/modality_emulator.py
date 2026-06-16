import datetime
import os
import time

import numpy as np
from dotenv import load_dotenv
from PIL import Image
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from pynetdicom import AE
from pynetdicom.sop_class import (
    DigitalMammographyXRayImageStorageForPresentation,  # type: ignore
    ModalityWorklistInformationFind,  # type: ignore
)

from environment import Environment
from services.dicom import PENDING, PENDING_WARNING, SUCCESS
from services.mwl import MWLStatus
from services.storage import MWLStorage
from telemetry import configure_logging

load_dotenv()

logger = configure_logging("Gateway-Emulator")


DICOM_LATERALITIES = ["L", "R"]
DICOM_VIEWS = ["CC", "MLO", "CCID"]
EMULATED_PROCEDURE_DURATION_SECONDS = int(os.getenv("EMULATED_PROCEDURE_DURATION_SECONDS", "5"))
MODALITY = "MG"
MWL_AET = os.getenv("MWL_AET", "SCREENING_MWL")
MWL_DB_PATH = os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")
MWL_HOST = os.getenv("MWL_HOST", "localhost")
MWL_PORT = int(os.getenv("MWL_PORT", "4243"))
PACS_AET = os.getenv("PACS_AET", "SCREENING_PACS")
PACS_DB_PATH = os.getenv("PACS_DB_PATH", "/var/lib/pacs/pacs.db")
PACS_HOST = os.getenv("PACS_HOST", "localhost")
PACS_PORT = int(os.getenv("PACS_PORT", "4244"))
SAMPLE_IMAGES_PATH = os.getenv("SAMPLE_IMAGES_PATH", "sample_images")


class DicomExample:
    def __init__(
        self, dataset: Dataset | None, laterality: str, view: str, study_instance_uid: str, series_number: int
    ):
        self.dataset = dataset
        self.laterality = laterality
        self.view = view
        self.study_instance_uid = study_instance_uid
        self.series_number = series_number
        self.data = self.generate_dicom()

    def generate_dicom(self) -> Dataset:
        ds = Dataset()
        if not self.dataset:
            logger.error("No dataset provided for DICOM generation")
            return ds

        img_path = f"{SAMPLE_IMAGES_PATH}/L{self.view.replace('ID', '')}.jpg"
        img = Image.open(img_path).convert("L")
        if self.laterality == "R":
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
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

        ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.Rows = rows
        ds.Columns = columns
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.PixelData = pixel_bytes
        ds.ImageLaterality = self.laterality
        ds.ViewPosition = self.view

        ds.AccessionNumber = self.dataset.AccessionNumber
        ds.PatientID = self.dataset.PatientID
        ds.PatientName = self.dataset.PatientName
        ds.PatientBirthDate = self.dataset.PatientBirthDate
        ds.PatientSex = self.dataset.PatientSex
        scheduled_step = self.dataset.ScheduledProcedureStepSequence[0]
        ds.StudyDate = scheduled_step.ScheduledProcedureStepStartDate
        ds.StudyTime = scheduled_step.ScheduledProcedureStepStartTime
        ds.StudyInstanceUID = self.study_instance_uid
        ds.StudyID = f"STUDY{self.study_instance_uid[-8:]}"
        ds.SeriesInstanceUID = generate_uid()
        ds.SeriesNumber = self.series_number
        ds.Modality = MODALITY
        ds.InstanceNumber = 1

        if self.view.endswith("ID"):
            view_modifier_code_sequence = Dataset()
            view_modifier_code_sequence.CodeValue = "R-102D5"
            view_modifier_code_sequence.CodingSchemeDesignator = "SRT"
            view_modifier_code_sequence.CodeMeaning = "Implant Displaced"
            ds.ViewModifierCodeSequence = [view_modifier_code_sequence]

        ds.file_meta = file_meta

        logger.debug(f"Generated DICOM for worklist item {self.dataset.AccessionNumber} - {self.laterality}{self.view}")
        logger.debug(f"{ds}")

        return ds


class ModalityEmulator:
    def __init__(self, mwl_storage: MWLStorage):
        self.mwl_storage = mwl_storage
        self.processed_items = set()

    def process_worklist_items(self, ae: AE):
        """
        Queries the MWL for items scheduled for today and sends generated DICOM files to the PACS server for each item.
        """
        mwl_assoc = ae.associate(MWL_HOST, MWL_PORT, ae_title=MWL_AET)
        pacs_assoc = ae.associate(PACS_HOST, PACS_PORT, ae_title=PACS_AET)

        if mwl_assoc.is_established and pacs_assoc.is_established:
            logger.info(f"Connected to MWL server {MWL_HOST}:{MWL_PORT} ({MWL_AET})")
            logger.info(f"Connected to PACS server {PACS_HOST}:{PACS_PORT} ({PACS_AET})")

            logger.info("Querying MWL for scheduled items...")
            responses = mwl_assoc.send_c_find(self.c_find_dataset, query_model=ModalityWorklistInformationFind)
            for status, ds in responses:
                status_code = getattr(status, "Status", SUCCESS)

                if status_code in (PENDING, PENDING_WARNING):
                    accession_number = getattr(ds, "AccessionNumber", "UNKNOWN")

                    if accession_number in self.processed_items:
                        logger.info(f"Skipping already processed worklist item {accession_number}")
                        continue

                    self.processed_items.add(accession_number)
                    study_instance_uid = generate_uid()
                    series_number = 1
                    for laterality in DICOM_LATERALITIES:
                        for view in DICOM_VIEWS:
                            logger.info(
                                f"Processing worklist item {accession_number} - generating DICOM for {laterality}{view}"
                            )
                            dicom_example = DicomExample(ds, laterality, view, study_instance_uid, series_number)
                            dataset = dicom_example.data

                            if getattr(dataset, "SOPInstanceUID", None) is None:
                                logger.error(
                                    f"Skipping DICOM generation for {laterality}{view} of worklist item {accession_number}"
                                )
                                continue

                            pacs_assoc.send_c_store(dataset)
                            logger.info(
                                f"Sent DICOM for {laterality}{view} of worklist item {accession_number}. Series# {series_number}"
                            )
                            series_number += 1

                    time.sleep(1)  # Allow C-STORE operations to complete before updating status

                    self.mwl_storage.update_status(accession_number, MWLStatus.COMPLETED.value)
                    logger.info(f"Completed processing for worklist item {accession_number}")
                elif status_code == SUCCESS:
                    logger.info("C-FIND query completed successfully")
                else:
                    logger.error(f"C-FIND query failed with status: 0x{status_code:04X}")

        else:
            logger.error("Failed to make MWL and PACS associations")

        mwl_assoc.release()
        pacs_assoc.release()

    @property
    def c_find_dataset(self) -> Dataset:
        date_today = datetime.date.today()
        ds = Dataset()
        sps_dataset = Dataset()
        sps_dataset.Modality = MODALITY
        sps_dataset.ScheduledProcedureStepStartDate = date_today.strftime("%Y%m%d")
        sps_dataset.ScheduledProcedureStepStartTime = "000000-"
        ds.ScheduledProcedureStepSequence = [sps_dataset]
        return ds


def main():
    if Environment().production:
        raise RuntimeError("Modality Emulator should not be run in production environment")

    logger.info("Modality Emulator Starting...")
    mwl_storage = MWLStorage(db_path=MWL_DB_PATH)
    emulator = ModalityEmulator(mwl_storage)
    ae = AE(ae_title="ModalityEmulator")
    ae.add_requested_context(DigitalMammographyXRayImageStorageForPresentation)
    ae.add_requested_context(ModalityWorklistInformationFind)

    while True:
        try:
            time.sleep(EMULATED_PROCEDURE_DURATION_SECONDS)
            emulator.process_worklist_items(ae)
        except KeyboardInterrupt:
            logger.warning("\n Modality Emulator shutting down...")
            break
        except Exception:
            logger.exception("Error in Modality Emulator")
            time.sleep(5)  # Wait before retrying to avoid tight error loop


if __name__ == "__main__":
    main()
