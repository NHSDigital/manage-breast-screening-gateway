"""DICOM Validation utilities."""

import logging

from pydicom import Dataset

logger = logging.getLogger(__name__)


class DicomValidationError(Exception):
    """Raised when DICOM validation fails."""

    pass


class DicomValidator:
    REQUIRED_TAGS = ["SOPInstanceUID", "PatientID", "StudyInstanceUID", "SOPClassUID"]
    DICOM_PREFIX = b"DICM"
    PREAMBLE_LENGTH = 128

    def validate_dataset(self, ds: Dataset) -> None:
        """Validate dataset has required DICOM tags."""
        for tag in self.REQUIRED_TAGS:
            value = ds.get(tag)
            if not value:
                raise DicomValidationError(f"Missing required tag: {tag}")

    def validate_bytes(self, data: bytes) -> None:
        """Validate serialized DICOM bytes have valid preamble."""
        min_size = self.PREAMBLE_LENGTH + len(self.DICOM_PREFIX)
        if len(data) < min_size:
            raise DicomValidationError(f"DICOM too small ({len(data)} bytes), missing preamble")

        preamble = data[self.PREAMBLE_LENGTH : self.PREAMBLE_LENGTH + 4]
        if preamble != self.DICOM_PREFIX:
            raise DicomValidationError(f"Invalid DICOM prefix: {preamble!r}, expected {self.DICOM_PREFIX!r}")

    def validate_pixel_data(self, ds: Dataset) -> None:
        """Validate pixel data consistency if present."""
        if not hasattr(ds, "PixelData") or ds.PixelData is None:
            return  # No pixel data to validate

        required_image_tags = ["Rows", "Columns", "BitsAllocated"]
        for tag in required_image_tags:
            if not hasattr(ds, tag):
                raise DicomValidationError(f"Image has PixelData but missing {tag}")
