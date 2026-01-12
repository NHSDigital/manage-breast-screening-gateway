"""DICOM Image Compression Service

Provides compression functionality for DICOM images using JPEG 2000 Lossy compression.
"""

import logging

from pydicom import Dataset
from pydicom.pixels.utils import compress
from pydicom.uid import JPEG2000, ExplicitVRLittleEndian

logger = logging.getLogger(__name__)


class ImageCompressor:
    def __init__(self, compression_ratio: int = 200):
        self.compression_ratio = compression_ratio

    def compress(self, ds: Dataset) -> Dataset:
        try:
            if not hasattr(ds, "PixelData") or ds.PixelData is None:
                logger.info("No pixel data found, skipping compression")
                return ds

            original_transfer_syntax = ds.file_meta.TransferSyntaxUID

            # Decompress if already compressed
            if original_transfer_syntax != ExplicitVRLittleEndian:
                logger.info(f"Decompressing from {original_transfer_syntax.name}")
                ds.decompress()
                ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

            compressed_ds = compress(
                ds, transfer_syntax_uid=JPEG2000, encoding_plugin="pylibjpeg", j2k_cr=[self.compression_ratio]
            )

            logger.info(f"Compressed to {compressed_ds.file_meta.TransferSyntaxUID.name} ({self.compression_ratio}:1)")

            return compressed_ds

        except Exception as e:
            logger.error(f"Compression failed: {e}", exc_info=True)
            logger.warning("Returning uncompressed dataset due to compression failure")
            return ds
