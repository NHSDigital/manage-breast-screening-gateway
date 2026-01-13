"""DICOM Image Resizing Service

Provides resizing functionality for DICOM images while maintaining aspect ratio.
"""

import logging

import numpy as np
from PIL import Image
from pydicom import Dataset

logger = logging.getLogger(__name__)


class ImageResizer:
    def __init__(self, thumbnail_size: int = 512):
        self.thumbnail_size = thumbnail_size

    def _calculate_thumbnail_dimensions(self, original_cols: int, original_rows: int) -> tuple[int, int]:
        aspect_ratio = original_cols / original_rows
        if original_cols > original_rows:
            new_cols = self.thumbnail_size
            new_rows = int(self.thumbnail_size / aspect_ratio)
        else:
            new_rows = self.thumbnail_size
            new_cols = int(self.thumbnail_size * aspect_ratio)
        return new_cols, new_rows

    def _to_pil_image(self, pixel_array: np.ndarray, bits_allocated: int) -> tuple[Image.Image, dict]:
        normalization_info = {}

        if bits_allocated == 16:
            pixel_min = pixel_array.min()
            pixel_max = pixel_array.max()
            normalization_info = {"pixel_min": pixel_min, "pixel_max": pixel_max}

            if pixel_max > pixel_min:
                pixel_array_8bit = ((pixel_array - pixel_min) / (pixel_max - pixel_min) * 255).astype(np.uint8)
            else:
                # Handle uniform images (all same value)
                pixel_array_8bit = np.zeros_like(pixel_array, dtype=np.uint8)
            img = Image.fromarray(pixel_array_8bit, mode="L")
        else:
            img = Image.fromarray(pixel_array, mode="L")

        return img, normalization_info

    def _from_pil_image(self, img: Image.Image, bits_allocated: int, normalization_info: dict) -> np.ndarray:
        resized_array = np.array(img)

        # For 16-bit images, scale back to 16-bit range
        if bits_allocated == 16:
            pixel_min = normalization_info.get("pixel_min", 0)
            pixel_max = normalization_info.get("pixel_max", 0)

            if pixel_max > pixel_min:
                resized_array = (resized_array.astype(np.float32) / 255 * (pixel_max - pixel_min) + pixel_min).astype(
                    np.uint16
                )
            else:
                # Keep uniform image as is
                resized_array = resized_array.astype(np.uint16)

        return resized_array

    def resize(self, ds: Dataset) -> Dataset:
        original_rows = ds.Rows
        original_cols = ds.Columns

        # Skip if already smaller than thumbnail size
        if original_rows <= self.thumbnail_size and original_cols <= self.thumbnail_size:
            logger.info(
                f"Image {original_cols}x{original_rows} already smaller than {self.thumbnail_size}, skipping resize"
            )
            return ds

        # Calculate new dimensions
        new_cols, new_rows = self._calculate_thumbnail_dimensions(original_cols, original_rows)
        logger.info(f"Resizing from {original_cols}x{original_rows} to {new_cols}x{new_rows}")

        # Convert DICOM to PIL Image
        pixel_array = ds.pixel_array
        img, normalization_info = self._to_pil_image(pixel_array, ds.BitsAllocated)

        # Resize
        img_resized = img.resize((new_cols, new_rows), Image.Resampling.LANCZOS)

        # Convert back to DICOM pixel data
        resized_array = self._from_pil_image(img_resized, ds.BitsAllocated, normalization_info)

        # Update dataset
        ds.PixelData = resized_array.tobytes()
        ds.Rows = new_rows
        ds.Columns = new_cols

        return ds
