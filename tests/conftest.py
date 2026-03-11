import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from pydicom import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian
from pynetdicom.sop_class import (
    DigitalMammographyXRayImageStorageForPresentation,
)

sys.path.append(f"{Path(__file__).parent.parent}/src")


@pytest.fixture
def tmp_dir():
    return f"{Path(__file__).parent}/tmp"


@pytest.fixture(autouse=True)
def teardown(tmp_dir):
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)

    yield
    shutil.rmtree(tmp_dir)


# DICOM test fixtures
@pytest.fixture
def dicom_file_meta():
    """Create standard DICOM file meta information."""
    file_meta = FileMetaDataset()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.MediaStorageSOPClassUID = DigitalMammographyXRayImageStorageForPresentation
    return file_meta


@pytest.fixture
def dataset_with_pixels(dicom_file_meta):
    """Create a DICOM dataset with pixel data (256x256, 16-bit)."""
    ds = Dataset()
    ds.Rows = 256
    ds.Columns = 256
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = np.zeros((256, 256), dtype=np.uint16).tobytes()
    ds.file_meta = dicom_file_meta
    return ds


@pytest.fixture
def dataset_without_pixels(dicom_file_meta):
    """Create a DICOM dataset without pixel data."""
    ds = Dataset()
    ds.PatientID = "123456"
    ds.PatientName = "TEST^PATIENT"
    ds.file_meta = dicom_file_meta
    return ds


@pytest.fixture
def listener_payload():
    return {
        "action_id": "action-12345",
        "action_type": "worklist.create_item",
        "parameters": {
            "worklist_item": {
                "participant": {
                    "nhs_number": "999123456",
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
                "accession_number": "ACC999999",
            }
        },
    }
