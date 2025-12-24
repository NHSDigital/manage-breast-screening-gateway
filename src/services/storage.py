"""
PACS Storage Layer

Manages DICOM image storage using hash-based directory structure and SQLite database.
Thread-safe implementation for concurrent access.
"""

import hashlib
import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Dict

logger = logging.getLogger(__name__)


class InstanceExistsError(Exception):
    pass


class PACSStorage:
    """Thread-safe PACS storage manager with hash-based file organization."""

    def __init__(self, db_path: str = "/var/lib/pacs/pacs.db", storage_root: str = "/var/lib/pacs/storage"):
        """
        Initialize PACS storage.

        Args:
            db_path: Path to SQLite database
            storage_root: Root directory for DICOM file storage
        """
        self.db_path = db_path
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

        # Ensure database is initialized
        self._ensure_db()

        # Enable WAL mode for better concurrent access
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.commit()

        logger.info(f"PACS storage initialized: db={db_path}, storage={storage_root}")

    def _ensure_db(self):
        """Ensure database exists and has correct schema."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            if conn:
                conn.close()

    def _compute_storage_path(self, sop_instance_uid: str) -> str:
        """
        Compute hash-based storage path for a SOP Instance UID.

        Uses first 2 chars of hash as first level, next 2 as second level.
        Example: "1.2.3.4.5" -> hash -> "a1/b2/a1b2c3d4e5f6.dcm"

        Args:
            sop_instance_uid: SOP Instance UID

        Returns:
            Relative path for storage
        """
        # Hash the UID to get consistent path
        hex = hashlib.sha256(sop_instance_uid.encode()).hexdigest()

        return f"{hex[:2]}/{hex[2:4]}/{hex[:16]}.dcm"

    def store_instance(
        self, sop_instance_uid: str, file_data: bytes, metadata: Dict, source_aet: str = "UNKNOWN"
    ) -> str:
        """
        Store a DICOM instance.

        Args:
            sop_instance_uid: SOP Instance UID
            file_data: Raw DICOM file bytes
            metadata: Dictionary of DICOM metadata
            source_aet: AE Title of sender

        Returns:
            Absolute path where file was stored

        Raises:
            InstanceExistsError: If instance already exists
        """
        with self._lock:
            if self.instance_exists(sop_instance_uid):
                raise InstanceExistsError(f"Instance already exists: {sop_instance_uid}")

            rel_path, abs_path, file_size, storage_hash = self.store_file(sop_instance_uid, file_data)

            # Store metadata in database
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO stored_instances (
                        sop_instance_uid, storage_path, file_size, storage_hash,
                        patient_id, patient_name, accession_number, source_aet,
                        status
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        'STORED'
                    )
                """,
                    (
                        sop_instance_uid,
                        str(rel_path),
                        file_size,
                        storage_hash,
                        metadata.get("patient_id"),
                        metadata.get("patient_name"),
                        metadata.get("accession_number"),
                        source_aet,
                    ),
                )
                conn.commit()

            logger.info(f"Stored instance: {sop_instance_uid} -> {rel_path} ({file_size} bytes)")

            return str(abs_path)

    def instance_exists(self, sop_instance_uid: str) -> bool:
        """Check if instance exists in database."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM stored_instances WHERE sop_instance_uid = ? AND status = 'STORED'", (sop_instance_uid,)
            )
            return cursor.fetchone() is not None

    def store_file(self, sop_instance_uid: str, file_data: bytes) -> tuple[str, Path, int, str]:
        rel_path = self._compute_storage_path(sop_instance_uid)
        abs_path = self.storage_root / rel_path

        abs_path.parent.mkdir(parents=True, exist_ok=True)

        abs_path.write_bytes(file_data)
        file_size = len(file_data)

        storage_hash = hashlib.sha256(file_data).hexdigest()

        return (rel_path, abs_path, file_size, storage_hash)

    def close(self):
        """Close storage (cleanup if needed)."""
        logger.info("PACS storage closed")
