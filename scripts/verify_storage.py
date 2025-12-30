#!/usr/bin/env python3
"""
Verify DICOM images stored in PACS.

Temporary script to query the PACS database and displays stored instances.
"""

import os
import sqlite3
import sys
from pathlib import Path


def get_db_path():
    return os.getenv("PACS_DB_PATH", "/var/lib/pacs/pacs.db")


def get_storage_path():
    return Path(os.getenv("PACS_STORAGE_PATH", "/var/lib/pacs/storage"))


def verify_storage():
    """Verify stored DICOM instances."""
    db_path = get_db_path()

    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get total count
    cursor.execute("SELECT COUNT(*) as count FROM stored_instances WHERE status = 'STORED'")
    total = cursor.fetchone()["count"]

    print(f"\n{'=' * 80}")
    print("PACS Storage Verification")
    print(f"{'=' * 80}\n")
    print(f"Database: {db_path}")
    print(f"Storage:  {get_storage_path()}\n")
    print(f"Total stored instances: {total}\n")

    if total == 0:
        print("No instances stored yet\n")
        conn.close()
        return True

    # Get all instances
    cursor.execute(
        """
        SELECT
            sop_instance_uid,
            patient_id,
            patient_name,
            accession_number,
            storage_path,
            file_size,
            source_aet,
            created_at
        FROM stored_instances
        WHERE status = 'STORED'
        ORDER BY created_at DESC
        LIMIT 10
        """
    )

    instances = cursor.fetchall()

    print(f"Most recent instances (showing {len(instances)} of {total}):\n")

    storage_root = get_storage_path()

    for i, instance in enumerate(instances, 1):
        print(f"{i}. SOP Instance UID: {instance['sop_instance_uid']}")
        print(f"   Patient ID:       {instance['patient_id'] or 'N/A'}")
        print(f"   Patient Name:     {instance['patient_name'] or 'N/A'}")
        print(f"   Accession Number: {instance['accession_number'] or 'N/A'}")
        print(f"   Source AET:       {instance['source_aet']}")
        print(f"   File Size:        {instance['file_size']:,} bytes")
        print(f"   Created:          {instance['created_at']}")

        # Verify file exists
        file_path = storage_root / instance["storage_path"]
        if file_path.exists():
            print(f"   File:             {instance['storage_path']}")
        else:
            print(f"   File:             Missing: {instance['storage_path']}")

        print()

    # Summary statistics
    cursor.execute(
        """
        SELECT
            COUNT(DISTINCT patient_id) as patients,
            COUNT(DISTINCT accession_number) as accessions,
            SUM(file_size) as total_size
        FROM stored_instances
        WHERE status = 'STORED'
        """
    )
    stats = cursor.fetchone()

    print(f"{'=' * 80}")
    print("Summary Statistics:")
    print(f"  Unique patients:        {stats['patients']}")
    print(f"  Unique accession nums:  {stats['accessions']}")
    print(f"  Total storage size:     {stats['total_size']:,} bytes ({stats['total_size'] / 1024 / 1024:.2f} MB)")
    print(f"{'=' * 80}\n")

    conn.close()
    return True


def main():
    """Main entry point."""
    try:
        success = verify_storage()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
