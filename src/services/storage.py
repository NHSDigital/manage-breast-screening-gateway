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
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class InstanceExistsError(Exception):
    pass


class Storage:
    def __init__(self, db_path: str, schema_path: str, table_name: str):
        """"""
        self.db_path = db_path
        self.schema_path = schema_path
        self.table_name = table_name
        self._ensure_db()

        # Enable WAL mode for better concurrent access
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.commit()

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

    def _ensure_db(self):
        """Ensure database exists and has correct schema."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        with self._get_connection() as conn:
            cursor = conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{self.table_name}'")
            if cursor.fetchone() is None:
                logger.info(f"Initializing database schema from {self.schema_path}")
                conn.executescript(Path(self.schema_path).read_text())
                conn.commit()


class PACSStorage(Storage):
    """PACS storage manager with hash-based file organization."""

    def __init__(self, db_path: str = "/var/lib/pacs/pacs.db", storage_root: str = "/var/lib/pacs/storage"):
        """
        Initialize PACS storage.

        Args:
            db_path: Path to SQLite database
            storage_root: Root directory for DICOM file storage
        """
        super().__init__(db_path, f"{Path(__file__).parent}/init_pacs_db.sql", "stored_instances")
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)

        logger.info(f"PACS storage initialized: db={db_path}, storage={storage_root}")

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


class WorklistStorage(Storage):
    def __init__(self, db_path: str = "/var/lib/pacs/worklist.db"):
        """
        Initialize Worklist storage.

        Args:
            db_path: Path to SQLite database
        """
        super().__init__(db_path, f"{Path(__file__).parent}/init_worklist_db.sql", "worklist_items")
        logger.info(f"Worklist storage initialized: db={db_path}")

    def store_worklist_item(
        self,
        accession_number: str,
        patient_id: str,
        patient_name: str,
        patient_birth_date: str,
        scheduled_date: str,
        scheduled_time: str,
        modality: str,
        study_description: str = "",
        patient_sex: str = "",
        procedure_code: str = "",
        study_instance_uid: str = "",
        source_message_id: str = "",
    ) -> str:
        """
        Add a new worklist item.

        Args:
            accession_number: Unique accession number (primary key)
            patient_id: Patient identifier
            patient_name: Patient name in DICOM format (e.g., "SMITH^JANE")
            patient_birth_date: Birth date in YYYYMMDD format
            scheduled_date: Scheduled date in YYYYMMDD format
            scheduled_time: Scheduled time in HHMMSS format
            modality: Modality code (e.g., "MG" for mammography)
            study_description: Description of the study
            patient_sex: Patient sex (M/F/O)
            procedure_code: Procedure code
            study_instance_uid: DICOM Study Instance UID
            source_message_id: ID of the relay message that created this item

        Returns:
            The accession number of the created item

        Raises:
            sqlite3.IntegrityError: If accession number already exists
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO worklist_items (
                    accession_number, patient_id, patient_name, patient_birth_date,
                    patient_sex, scheduled_date, scheduled_time, modality,
                    study_description, procedure_code, study_instance_uid,
                    source_message_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    accession_number,
                    patient_id,
                    patient_name,
                    patient_birth_date,
                    patient_sex,
                    scheduled_date,
                    scheduled_time,
                    modality,
                    study_description,
                    procedure_code,
                    study_instance_uid,
                    source_message_id,
                ),
            )
            conn.commit()

        return accession_number

    def find_worklist_items(
        self,
        modality: Optional[str] = None,
        scheduled_date: Optional[str] = None,
        patient_id: Optional[str] = None,
        status: str = "SCHEDULED",
    ) -> List[sqlite3.Row]:
        """
        Query worklist items with optional filters.

        Args:
            modality: Filter by modality (e.g., "MG")
            scheduled_date: Filter by scheduled date (YYYYMMDD)
            patient_id: Filter by patient ID
            status: Filter by status (default: "SCHEDULED")

        Returns:
            List of worklist items as dictionaries
        """
        query = "SELECT * FROM worklist_items WHERE status = ?"
        params = [status]

        if modality:
            query += " AND modality = ?"
            params.append(modality)

        if scheduled_date:
            query += " AND scheduled_date = ?"
            params.append(scheduled_date)

        if patient_id:
            query += " AND patient_id = ?"
            params.append(patient_id)

        query += " ORDER BY scheduled_date, scheduled_time"

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)

            return [row for row in cursor.fetchall()]

    def get_worklist_item(self, accession_number: str) -> Optional[Dict]:
        """
        Get a single worklist item by accession number.

        Args:
            accession_number: The accession number to look up

        Returns:
            Worklist item as dictionary, or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM worklist_items WHERE accession_number = ?", (accession_number,))
            row = cursor.fetchone()

        return dict(row) if row else None

    def update_status(
        self, accession_number: str, status: str, mpps_instance_uid: Optional[str] = None
    ) -> Optional[str]:
        """
        Update the status of a worklist item.

        Args:
            accession_number: The accession number to update
            status: New status (SCHEDULED, IN_PROGRESS, COMPLETED, DISCONTINUED)
            mpps_instance_uid: Optional MPPS instance UID

        Returns:
            source_message_id if item was updated, None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE worklist_items
                SET status = ?,
                    mpps_instance_uid = COALESCE(?, mpps_instance_uid),
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession_number = ?
            """,
                (status, mpps_instance_uid, accession_number),
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            result = conn.execute(
                "SELECT source_message_id FROM worklist_items WHERE accession_number = ?", (accession_number,)
            ).fetchone()

            return result["source_message_id"] if result is not None else None

    def update_study_instance_uid(self, accession_number: str, study_instance_uid: str) -> bool:
        """
        Update the study instance UID for a worklist item.

        Args:
            accession_number: The accession number to update
            study_instance_uid: The Study Instance UID

        Returns:
            True if item was updated, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE worklist_items
                SET study_instance_uid = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession_number = ?
            """,
                (study_instance_uid, accession_number),
            )
            conn.commit()

            return cursor.rowcount > 0

    def delete_worklist_item(self, accession_number: str) -> bool:
        """
        Delete a worklist item.

        Args:
            accession_number: The accession number to delete

        Returns:
            True if item was deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM worklist_items WHERE accession_number = ?", (accession_number,))
            conn.commit()
            return cursor.rowcount > 0
