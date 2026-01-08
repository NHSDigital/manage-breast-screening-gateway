#!/usr/bin/env python3
"""
Command-line utility to add worklist items to the database.

Usage:
    python add_worklist_item.py --accession ACC111 --patient-id 9990001112 \
        --patient-name "SMITH^JANE" --birth-date 19800201 --sex F \
        --date 20251118 --time 143000 --modality MG \
        --description "Screening Mammography" \
        --db-path ./worklist.db
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, f"{Path(__file__).parent.parent}/src")

from services.storage import MWLStorage


def main():
    parser = argparse.ArgumentParser(
        description="Add a worklist item to the database", formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--accession", required=True, help="Accession number (unique)")
    parser.add_argument("--patient-id", required=True, help="Patient ID")
    parser.add_argument("--patient-name", required=True, help="Patient name in DICOM format (FAMILY^GIVEN)")
    parser.add_argument("--birth-date", required=True, help="Birth date (YYYYMMDD)")
    parser.add_argument("--sex", choices=["M", "F", "O"], default="", help="Patient sex")
    parser.add_argument("--date", help="Scheduled date (YYYYMMDD, default: today)")
    parser.add_argument("--time", default="090000", help="Scheduled time (HHMMSS, default: 090000)")
    parser.add_argument("--modality", default="MG", help="Modality code (default: MG)")
    parser.add_argument("--description", default="", help="Study description")
    parser.add_argument("--procedure-code", default="", help="Procedure code")
    parser.add_argument(
        "--db-path",
        default="/var/lib/worklist/worklist.db",
        help="Path to database (default: /var/lib/worklist/worklist.db)",
    )

    args = parser.parse_args()

    # Default to today if date not provided
    scheduled_date = args.date if args.date else datetime.now().strftime("%Y%m%d")

    # Initialize storage
    try:
        storage = MWLStorage(db_path=args.db_path)
    except Exception as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        return 1

    # Add the worklist item
    try:
        storage.store_worklist_item(
            accession_number=args.accession,
            patient_id=args.patient_id,
            patient_name=args.patient_name,
            patient_birth_date=args.birth_date,
            scheduled_date=scheduled_date,
            scheduled_time=args.time,
            modality=args.modality,
            study_description=args.description,
            patient_sex=args.sex,
            procedure_code=args.procedure_code,
        )

        print(f"✓ Successfully added worklist item: {args.accession}")
        print(f"  Patient: {args.patient_name} ({args.patient_id})")
        print(f"  Scheduled: {scheduled_date} at {args.time}")
        print(f"  Modality: {args.modality}")

        return 0

    except Exception as e:
        print(f"✗ Error adding worklist item: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
