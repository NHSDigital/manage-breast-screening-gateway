import numpy as np
from pydicom.uid import ExplicitVRLittleEndian

from services.dicom.image_resizer import ImageResizer


class TestImageResizer:
    def test_resize_large_image_maintains_aspect_ratio(self, dataset_with_pixels):
        """Test resizing large images maintains aspect ratio."""
        dataset_with_pixels.Rows = 4000
        dataset_with_pixels.Columns = 3000
        dataset_with_pixels.PixelData = np.zeros((4000, 3000), dtype=np.uint16).tobytes()

        subject = ImageResizer(thumbnail_size=512)
        resized_ds = subject.resize(dataset_with_pixels)

        assert resized_ds.Columns == 384
        assert resized_ds.Rows == 512
        assert resized_ds.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian

    def test_resize_skips_small_images(self, dataset_with_pixels):
        """Test that images smaller than thumbnail size are not upscaled."""
        # 256x256 is smaller than default 512 thumbnail
        subject = ImageResizer()
        resized_ds = subject.resize(dataset_with_pixels)

        assert resized_ds.Rows == 256
        assert resized_ds.Columns == 256

    def test_resize_preserves_bit_depth(self, dataset_with_pixels):
        dataset_with_pixels.Rows = 1000
        dataset_with_pixels.Columns = 1000
        dataset_with_pixels.BitsAllocated = 16
        dataset_with_pixels.PixelData = np.zeros((1000, 1000), dtype=np.uint16).tobytes()

        subject = ImageResizer(thumbnail_size=512)
        resized_ds = subject.resize(dataset_with_pixels)

        assert resized_ds.BitsAllocated == 16
