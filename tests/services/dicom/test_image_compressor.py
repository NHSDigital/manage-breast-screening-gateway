from io import BytesIO
from unittest.mock import patch

import pydicom
from pydicom.uid import JPEG2000, ExplicitVRLittleEndian

from services.dicom.image_compressor import ImageCompressor


class TestImageCompressor:
    # Fixtures dataset_with_pixels and dataset_without_pixels
    # are available from conftest.py

    def test_compress_applies_jpeg2000_compression(self, dataset_with_pixels):
        subject = ImageCompressor()
        compressed_ds = subject.compress(dataset_with_pixels)

        assert compressed_ds.file_meta.TransferSyntaxUID == JPEG2000

        # Verify we can serialize the compressed dataset
        buffer = BytesIO()
        pydicom.dcmwrite(buffer, compressed_ds)
        assert len(buffer.getvalue()) > 0

    def test_compress_dataset_without_pixel_data(self, dataset_without_pixels):
        """Test compression skips datasets without pixel data."""
        subject = ImageCompressor()
        result = subject.compress(dataset_without_pixels)

        # Should return original dataset unchanged
        assert result == dataset_without_pixels
        assert result.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian

    def test_compress_dataset_with_none_pixel_data(self, dataset_with_pixels):
        """Test compression handles None pixel data gracefully."""
        dataset_with_pixels.PixelData = None
        subject = ImageCompressor()

        result = subject.compress(dataset_with_pixels)

        # Should return original dataset unchanged
        assert result == dataset_with_pixels
        assert result.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian

    def test_compress_already_compressed_dataset(self, dataset_with_pixels):
        """Test compression handles already-compressed datasets gracefully."""
        subject = ImageCompressor(compression_ratio=100)
        compressed_once = subject.compress(dataset_with_pixels)

        subject_200 = ImageCompressor(compression_ratio=200)
        compressed_twice = subject_200.compress(compressed_once)

        assert compressed_twice.file_meta.TransferSyntaxUID == JPEG2000

    @patch("services.dicom.image_compressor.compress")
    def test_compress_failure_returns_original(self, mock_compress, dataset_with_pixels):
        """Test compression failure returns original dataset."""
        mock_compress.side_effect = Exception("Compression failed!")

        subject = ImageCompressor()
        result = subject.compress(dataset_with_pixels)

        # Should return original dataset on failure
        assert result == dataset_with_pixels
        assert result.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian

    def test_compress_preserves_metadata(self, dataset_with_pixels):
        """Test that compression preserves dataset metadata."""
        dataset_with_pixels.PatientID = "123456"
        dataset_with_pixels.PatientName = "TEST^PATIENT"
        dataset_with_pixels.StudyDescription = "Test Study"

        subject = ImageCompressor()
        compressed_ds = subject.compress(dataset_with_pixels)

        assert compressed_ds.PatientID == "123456"
        assert compressed_ds.PatientName == "TEST^PATIENT"
        assert compressed_ds.StudyDescription == "Test Study"
        assert compressed_ds.Rows == 256
        assert compressed_ds.Columns == 256
