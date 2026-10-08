"""Single source for environment configuration shared across services.

Every value the deploy pipeline writes to .env that more than one module
reads is resolved here, so the services and the health check don't
drift apart in how they interpret a missing variable.

These are functions, not module-level constants, so values are resolved
at call time - after the entry point's load_dotenv() has run.
"""

import os
from urllib import parse

API_PATH = "/api/v1/dicom"
RUBIE_DOMAIN = "run-breast-screening.nhs.uk"


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


def cloud_api_endpoint(base_url: str | None = None) -> str:
    """
    Return the cloud API endpoint, optionally overriding the scheme and netloc
    """
    api_endpoint = os.getenv("CLOUD_API_ENDPOINT", f"http://localhost:8000{API_PATH}")
    if base_url:
        split_base_url = parse.urlsplit(base_url)
        split_endpoint = parse.urlsplit(api_endpoint)
        split_endpoint = split_endpoint._replace(scheme=split_base_url.scheme, netloc=split_base_url.netloc)
        return parse.urlunsplit(split_endpoint)
    return api_endpoint


def log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO").upper()


def log_format() -> str:
    return os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
