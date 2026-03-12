from datetime import datetime
import dotenv
import sqlite3
import os
import sys

dotenv.load_dotenv()


def backup_database(db_path, backup_path):
    """Backup the database at db_path."""

    conn = None

    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return False

    if not os.path.exists(backup_path):
        os.makedirs(backup_path)

    try:
        date_and_time = datetime.now().strftime("%Y%m%d-%H%M%S")
        db_filename = os.path.basename(db_path)
        backup_path = f"{backup_path}/{date_and_time}.{db_filename}.backup"

        conn = sqlite3.connect(db_path)
        with sqlite3.connect(backup_path) as backup_conn:
            conn.backup(backup_conn)
        print(f"Database backed up successfully to: {backup_path}")
        return True
    except Exception as e:
        print(f"Error during backup: {e}")
        return False
    finally:
        if conn:
            conn.close()


def main():
    """Main entry point."""
    try:
        pacs_db_path = os.getenv("PACS_DB_PATH")
        mwl_db_path = os.getenv("MWL_DB_PATH")
        backup_path = os.getenv("BACKUP_PATH", "./backups")

        print("Starting database backup...")
        print("PACS_DB_PATH:", pacs_db_path, "MWL_DB_PATH:", mwl_db_path)
        success = True

        if pacs_db_path:
            print(f"Backing up PACS database: {pacs_db_path} to {backup_path}")
            success = success and backup_database(pacs_db_path, backup_path)
        else:
            print("PACS_DB_PATH not set, skipping PACS database backup")

        if mwl_db_path:
            print(f"Backing up MWL database: {mwl_db_path} to {backup_path}")
            success = success and backup_database(mwl_db_path, backup_path)
        else:
            print("MWL_DB_PATH not set, skipping MWL database backup")

        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
