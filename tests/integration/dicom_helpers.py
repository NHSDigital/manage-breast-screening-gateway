"""
DICOM Helpers - Supporting functions for integration tests.

This module contains handler functions for generating and sending DICOM files.
"""

import datetime
import logging
import os
import random
import tempfile

import numpy as np
import pydicom
from pydicom import dcmwrite
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from pynetdicom import AE
from pynetdicom.sop_class import (
    DigitalMammographyXRayImageStorageForPresentation,
    DigitalMammographyXRayImageStorageForProcessing,
)


def generate_random_dicom_file(modality_type="MG"):
    """
    Handler function to generate a random DICOM mammography file with basic image data

    :param modality_type: Type of modality (defaults to MG for mammography)
    :return: Path to the generated DICOM file
    """
    # Create a temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".dcm")
    temp_file.close()
    file_path = temp_file.name

    # Create a basic DICOM dataset for mammography
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = DigitalMammographyXRayImageStorageForPresentation
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.ImplementationClassUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    # Create the main dataset
    ds = FileDataset(file_path, {}, file_meta=file_meta, preamble=b"\0" * 128)

    # Add required DICOM tags
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID

    # Patient information
    ds.PatientName = f"RANDOM^{random.choice(['SMITH', 'JOHNSON', 'WILLIAMS', 'BROWN', 'JONES', 'GARCIA', 'MILLER'])}"
    ds.PatientID = f"ID{random.randint(10000, 99999)}"
    ds.PatientBirthDate = f"{random.randint(1940, 2000):04d}{random.randint(1, 12):02d}{random.randint(1, 28):02d}"
    ds.PatientSex = random.choice(["M", "F", "O"])

    # Study information
    ds.StudyDate = datetime.date.today().strftime("%Y%m%d")
    ds.StudyTime = datetime.datetime.now().strftime("%H%M%S")
    ds.StudyInstanceUID = generate_uid()
    ds.StudyID = f"STUDY{random.randint(1000, 9999)}"
    ds.AccessionNumber = f"ACC{random.randint(100000, 999999)}"

    # Series information
    ds.SeriesInstanceUID = generate_uid()
    ds.SeriesNumber = random.randint(1, 100)
    ds.Modality = modality_type

    # Image information
    ds.InstanceNumber = random.randint(1, 1000)

    # Add some basic image pixel data
    # For demonstration, create a simple test pattern
    rows, cols = 256, 256
    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1  # Signed
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"

    # Create simple test pattern pixel data
    pixel_data = np.zeros((rows, cols), dtype=np.int16)

    # Add some pattern to make it more realistic
    for i in range(rows):
        for j in range(cols):
            # Create a pattern with random values and some gradients
            base_value = random.randint(-1000, 2000)
            gradient_x = int((j / cols) * 500)
            gradient_y = int((i / rows) * 500)
            circle_value = 0
            center_x, center_y = rows // 2, cols // 2
            distance = ((i - center_x) ** 2 + (j - center_y) ** 2) ** 0.5
            if distance < min(rows, cols) // 4:
                circle_value = 1000

            pixel_data[i, j] = base_value + gradient_x + gradient_y + circle_value

    # Add noise
    noise = np.random.normal(0, 50, (rows, cols)).astype(np.int16)
    pixel_data = pixel_data + noise

    ds.PixelData = pixel_data.tobytes()

    # Write the DICOM file
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dcmwrite(file_path, ds, enforce_file_format=False)

    logging.getLogger(__name__).info(f"Generated DICOM file: {file_path} with modality {modality_type}")
    return file_path


def send_dicom_file_to_server(
    dicom_file_path,
    server_address,
    server_port,
    server_ae_title,
    ae_title="RANDOM_MODALITY",
):
    """
    Handler function to send a DICOM file to a DICOM server using C-STORE

    :param dicom_file_path: Path to the DICOM file to send
    :param server_address: IP address of the DICOM server
    :param server_port: Port of the DICOM server
    :param server_ae_title: AE title of the DICOM server
    :param ae_title: Application Entity title for this modality (max 16 characters)
    :return: True if successful, False otherwise
    """
    try:
        # Load the DICOM file
        ds = pydicom.dcmread(dicom_file_path)

        # Create AE with specified AE title
        ae = AE(ae_title=ae_title[:16])  # Ensure max 16 characters

        # Add mammography presentation contexts
        ae.add_requested_context(DigitalMammographyXRayImageStorageForPresentation)
        ae.add_requested_context(DigitalMammographyXRayImageStorageForProcessing)

        # Create association with the server
        assoc = ae.associate(server_address, server_port, ae_title=server_ae_title)

        if assoc.is_established:
            logger = logging.getLogger(__name__)
            logger.info(f"Connected to server {server_address}:{server_port} ({server_ae_title})")

            # Send the C-STORE request
            status = assoc.send_c_store(ds)

            if status:
                # Check the status of the C-STORE operation
                if status.Status == 0x0000:
                    logger.info(f"Successfully sent DICOM file to server: {dicom_file_path}")
                    result = True
                else:
                    logger.error(f"C-STORE failed with status: 0x{status.Status:04X}")
                    result = False
            else:
                logger.error("C-STORE request failed - no status returned")
                result = False

            assoc.release()
            return result
        else:
            logging.getLogger(__name__).error(
                f"Failed to connect to server {server_address}:{server_port} ({server_ae_title})"
            )
            return False
    except Exception as e:
        logging.getLogger(__name__).error(f"Error sending DICOM file: {e}")
        return False


def send_random_dicom_series(
    num_files,
    server_address,
    server_port,
    server_ae_title,
    modality_type="CT",
    ae_title="RANDOM_MODALITY",
):
    """
    Handler function to generate and send multiple random DICOM files as a series

    :param num_files: Number of DICOM files to generate and send
    :param server_address: IP address of the DICOM server
    :param server_port: Port of the DICOM server
    :param server_ae_title: AE title of the DICOM server
    :param modality_type: Type of modality (CT, MR, PT, SC)
    :param ae_title: Application Entity title for this modality (max 16 characters)
    :return: Number of successfully sent files
    """
    success_count = 0
    logger = logging.getLogger(__name__)

    for i in range(num_files):
        try:
            # Generate random DICOM file
            dicom_file = generate_random_dicom_file(modality_type)

            # Send to server
            success = send_dicom_file_to_server(dicom_file, server_address, server_port, server_ae_title, ae_title)

            if success:
                success_count += 1
                logger.info(f"Successfully sent file {i + 1}/{num_files}")
            else:
                logger.error(f"Failed to send file {i + 1}/{num_files}")

            # Remove temporary file after sending
            if os.path.exists(dicom_file):
                os.remove(dicom_file)

        except Exception as e:
            logger.error(f"Error processing file {i + 1}: {e}")

    logger.info(f"Sent {success_count}/{num_files} files successfully")
    return success_count
