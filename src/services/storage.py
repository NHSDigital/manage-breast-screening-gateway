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
from typing import Optional, Dict, List

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
        hash_hex = hashlib.sha256(sop_instance_uid.encode()).hexdigest()

        # Use first 4 chars for two-level directory structure
        level1 = hash_hex[:2]
        level2 = hash_hex[2:4]

        # Use first 16 chars of hash as filename
        filename = f"{hash_hex[:16]}.dcm"

        return f"{level1}/{level2}/{filename}"

    def store_instance(
        self,
        sop_instance_uid: str,
        file_data: bytes,
        metadata: Dict,
        source_aet: str = "UNKNOWN"
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
            ValueError: If instance already exists
        """
        with self._lock:
            # Check if already exists
            if self.instance_exists(sop_instance_uid):
                raise InstanceExistsError(f"Instance already exists: {sop_instance_uid}")

            # Compute storage path
            rel_path = self._compute_storage_path(sop_instance_uid)
            abs_path = self.storage_root / rel_path

            # Create directory
            abs_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            abs_path.write_bytes(file_data)
            file_size = len(file_data)

            # Compute file hash for integrity
            storage_hash = hashlib.sha256(file_data).hexdigest()

            # Store metadata in database
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO stored_instances (
                        sop_instance_uid, storage_path, file_size, storage_hash,
                        patient_id, patient_name,
                        study_instance_uid, series_instance_uid,
                        accession_number, study_date, study_time, study_description,
                        series_number, series_description, modality,
                        instance_number,
                        view_position, laterality,
                        organ_dose, entrance_dose_in_mgy, kvp, exposure_in_uas,
                        anode_target_material, filter_material, filter_thickness,
                        transfer_syntax_uid, sop_class_uid,
                        rows, columns,
                        source_aet, status
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?,
                        ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?,
                        ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?,
                        ?, 'STORED'
                    )
                """, (
                    sop_instance_uid, str(rel_path), file_size, storage_hash,
                    metadata.get('patient_id'),
                    metadata.get('patient_name'),
                    metadata.get('study_instance_uid'),
                    metadata.get('series_instance_uid'),
                    metadata.get('accession_number'),
                    metadata.get('study_date'),
                    metadata.get('study_time'),
                    metadata.get('study_description'),
                    metadata.get('series_number'),
                    metadata.get('series_description'),
                    metadata.get('modality'),
                    metadata.get('instance_number'),
                    metadata.get('view_position'),
                    metadata.get('laterality'),
                    metadata.get('organ_dose'),
                    metadata.get('entrance_dose_in_mgy'),
                    metadata.get('kvp'),
                    metadata.get('exposure_in_uas'),
                    metadata.get('anode_target_material'),
                    metadata.get('filter_material'),
                    metadata.get('filter_thickness'),
                    metadata.get('transfer_syntax_uid'),
                    metadata.get('sop_class_uid'),
                    metadata.get('rows'),
                    metadata.get('columns'),
                    source_aet
                ))
                conn.commit()

            logger.info(f"Stored instance: {sop_instance_uid} -> {rel_path} ({file_size} bytes)")

            return str(abs_path)

    def instance_exists(self, sop_instance_uid: str) -> bool:
        """Check if instance exists in database."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM stored_instances WHERE sop_instance_uid = ? AND status = 'STORED'",
                (sop_instance_uid,)
            )
            return cursor.fetchone() is not None

    def get_instance_path(self, sop_instance_uid: str) -> Optional[Path]:
        """Get absolute path for a stored instance."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT storage_path FROM stored_instances WHERE sop_instance_uid = ? AND status = 'STORED'",
                (sop_instance_uid,)
            )
            row = cursor.fetchone()
            if row:
                return self.storage_root / row['storage_path']
            return None

    def find_instances(
        self,
        patient_id: Optional[str] = None,
        study_uid: Optional[str] = None,
        series_uid: Optional[str] = None,
        accession_number: Optional[str] = None,
        modality: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Find instances matching criteria.

        Returns list of dictionaries with instance metadata.
        """
        query = "SELECT * FROM stored_instances WHERE status = 'STORED'"
        params = []

        if patient_id:
            query += " AND patient_id = ?"
            params.append(patient_id)

        if study_uid:
            query += " AND study_instance_uid = ?"
            params.append(study_uid)

        if series_uid:
            query += " AND series_instance_uid = ?"
            params.append(series_uid)

        if accession_number:
            query += " AND accession_number = ?"
            params.append(accession_number)

        if modality:
            query += " AND modality = ?"
            params.append(modality)

        query += " ORDER BY received_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_statistics(self) -> Dict:
        """Get storage statistics."""
        with self._get_connection() as conn:
            # Get overall stats
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total_instances,
                    SUM(file_size) as total_size_bytes,
                    COUNT(DISTINCT study_instance_uid) as total_studies,
                    COUNT(DISTINCT series_instance_uid) as total_series,
                    COUNT(DISTINCT patient_id) as total_patients
                FROM stored_instances
                WHERE status = 'STORED'
            """)
            stats = dict(cursor.fetchone())

            # Get stats by modality
            cursor = conn.execute("""
                SELECT modality, COUNT(*) as count, SUM(file_size) as size_bytes
                FROM stored_instances
                WHERE status = 'STORED'
                GROUP BY modality
                ORDER BY count DESC
            """)
            stats['by_modality'] = [dict(row) for row in cursor.fetchall()]

            return stats

    def verify_integrity(self, sop_instance_uid: str) -> bool:
        """Verify file integrity using stored hash."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT storage_path, storage_hash FROM stored_instances WHERE sop_instance_uid = ?",
                (sop_instance_uid,)
            )
            row = cursor.fetchone()

            if not row:
                return False

            file_path = self.storage_root / row['storage_path']
            if not file_path.exists():
                logger.error(f"File missing: {file_path}")
                return False

            # Compute current hash
            current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

            if current_hash != row['storage_hash']:
                logger.error(f"Hash mismatch for {sop_instance_uid}")
                return False

            return True

    def close(self):
        """Close storage (cleanup if needed)."""
        logger.info("PACS storage closed")
