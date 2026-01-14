"""DICOM Image Compression Service

Provides compression functionality for DICOM images using JPEG 2000 Lossy compression.
"""

import logging
import os

from pydicom import Dataset
from pydicom.pixels.utils import compress
from pydicom.uid import JPEG2000, ExplicitVRLittleEndian

from services.dicom.image_resizer import ImageResizer

logger = logging.getLogger(__name__)


class ImageCompressor:
    def __init__(self, compression_ratio: int | None = None, resizer: ImageResizer | None = None):
        self.compression_ratio = (
            compression_ratio if compression_ratio is not None else int(os.getenv("DICOM_COMPRESSION_RATIO", "15"))
        )
        self.resizer = resizer or ImageResizer()

    def compress(self, ds: Dataset) -> Dataset:
        """
        Resize and compress DICOM image.

        Args:
            ds: DICOM dataset

        Returns:
            Best possible version of dataset given any failures
        """
        if not hasattr(ds, "PixelData") or ds.PixelData is None:
            logger.info("No pixel data found, skipping compression")
            return ds

        original_transfer_syntax = ds.file_meta.TransferSyntaxUID

        # Decompress if already compressed
        if ds.file_meta.TransferSyntaxUID not in UNCOMPRESSED_TRANSFER_SYNTAXES:
            try:
                logger.info(f"Decompressing from {original_transfer_syntax.name}")
                ds.decompress()
                ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            except Exception as e:
                logger.error(f"Decompression failed: {e}", exc_info=True)
                logger.warning("Continuing with compressed dataset")

        try:
            ds = self.resizer.resize(ds)
            logger.debug(f"Resized to {ds.Columns}×{ds.Rows}")
        except Exception as e:
            logger.error(f"Resizing failed: {e}", exc_info=True)
            logger.warning("Continuing with original size")

        try:
            compressed_ds = compress(
                ds, transfer_syntax_uid=JPEG2000, encoding_plugin="pylibjpeg", j2k_cr=[self.compression_ratio]
            )
            logger.info(
                f"Compressed to {compressed_ds.file_meta.TransferSyntaxUID.name} "
                f"({self.compression_ratio}:1, {compressed_ds.Columns}×{compressed_ds.Rows})"
            )
            return compressed_ds

        except Exception as e:
            logger.error(f"Compression failed: {e}", exc_info=True)
            logger.warning(
                f"Returning uncompressed dataset ({ds.Columns}×{ds.Rows}, ~{(ds.Columns * ds.Rows * 2) / 1024:.0f} KB)"
            )
            return ds
