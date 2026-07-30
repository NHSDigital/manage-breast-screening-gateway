"""Single source for environment configuration shared across services.

Every value the deploy pipeline writes to .env that more than one module
reads is resolved here, so the services and the health check don't
drift apart in how they interpret a missing variable.

These are functions, not module-level constants, so values are resolved
at call time - after the entry point's load_dotenv() has run.
"""

import os


def mwl_db_path() -> str:
    return os.getenv("MWL_DB_PATH", "/var/lib/pacs/worklist.db")


def pacs_db_path() -> str:
    return os.getenv("PACS_DB_PATH", "/var/lib/pacs/pacs.db")


def pacs_storage_path() -> str:
    return os.getenv("PACS_STORAGE_PATH", "/var/lib/pacs/storage")


def mwl_aet() -> str:
    return os.getenv("MWL_AET", "SCREENING_MWL")


def mwl_port() -> int:
    return int(os.getenv("MWL_PORT", "4243"))


def pacs_aet() -> str:
    return os.getenv("PACS_AET", "SCREENING_PACS")


def pacs_port() -> int:
    return int(os.getenv("PACS_PORT", "4244"))


def cloud_api_endpoint() -> str:
    return os.getenv("CLOUD_API_ENDPOINT", "http://localhost:8000/api/v1/dicom")


def log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO").upper()


def log_format() -> str:
    return os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
