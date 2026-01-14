from io import BytesIO
from unittest.mock import Mock, patch

import numpy as np
import pydicom
from pydicom.uid import JPEG2000, ExplicitVRLittleEndian

from services.dicom.image_compressor import ImageCompressor
from services.dicom.image_resizer import ImageResizer


class TestImageCompressor:
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
        subject = ImageCompressor(compression_ratio=100)
        compressed_once = subject.compress(dataset_with_pixels)

        subject_200 = ImageCompressor(compression_ratio=200)
        compressed_twice = subject_200.compress(compressed_once)

        assert compressed_twice.file_meta.TransferSyntaxUID == JPEG2000

    @patch("services.dicom.image_compressor.compress")
    def test_compress_failure_returns_resized_uncompressed(self, mock_compress, dataset_with_pixels):
        mock_compress.side_effect = Exception("Compression failed!")

        dataset_with_pixels.Rows = 1000
        dataset_with_pixels.Columns = 1000
        dataset_with_pixels.PixelData = np.zeros((1000, 1000), dtype=np.uint16).tobytes()

        subject = ImageCompressor()
        result = subject.compress(dataset_with_pixels)

        # Should return resized but uncompressed dataset
        assert result.Rows == 400
        assert result.Columns == 400
        assert result.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian

    def test_compress_preserves_metadata(self, dataset_with_pixels):
        dataset_with_pixels.PatientID = "123456"
        dataset_with_pixels.PatientName = "TEST^PATIENT"
        dataset_with_pixels.StudyDescription = "Test Study"

        subject = ImageCompressor()
        compressed_ds = subject.compress(dataset_with_pixels)

        assert compressed_ds.PatientID == "123456"
        assert compressed_ds.PatientName == "TEST^PATIENT"
        assert compressed_ds.StudyDescription == "Test Study"

    def test_resizer_is_called(self, dataset_with_pixels):
        mock_resizer = Mock(spec=ImageResizer)
        mock_resizer.resize.return_value = dataset_with_pixels

        subject = ImageCompressor(resizer=mock_resizer)
        subject.compress(dataset_with_pixels)

        mock_resizer.resize.assert_called_once()

    def test_compress_with_real_resizer(self, dataset_with_pixels):
        dataset_with_pixels.Rows = 3000
        dataset_with_pixels.Columns = 3000
        dataset_with_pixels.PixelData = np.zeros((3000, 3000), dtype=np.uint16).tobytes()

        resizer = ImageResizer(thumbnail_size=512)
        subject = ImageCompressor(resizer=resizer)
        compressed_ds = subject.compress(dataset_with_pixels)

        assert compressed_ds.Rows == 512
        assert compressed_ds.Columns == 512
        assert compressed_ds.file_meta.TransferSyntaxUID == JPEG2000

    def test_resize_failure_still_compresses(self, dataset_with_pixels):
        mock_resizer = Mock(spec=ImageResizer)
        mock_resizer.resize.side_effect = Exception("Resize failed!")

        subject = ImageCompressor(resizer=mock_resizer)
        result = subject.compress(dataset_with_pixels)

        assert result.Rows == 256
        assert result.Columns == 256
        assert result.file_meta.TransferSyntaxUID == JPEG2000

    def test_resize_and_compression_both_fail(self, dataset_with_pixels):
        mock_resizer = Mock(spec=ImageResizer)
        mock_resizer.resize.side_effect = Exception("Resize failed!")

        with patch("services.dicom.image_compressor.compress", side_effect=Exception("Compression failed!")):
            subject = ImageCompressor(resizer=mock_resizer)
            result = subject.compress(dataset_with_pixels)

            assert result.Rows == 256
            assert result.Columns == 256
            assert result.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian
