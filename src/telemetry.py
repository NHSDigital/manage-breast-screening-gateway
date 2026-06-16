import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Suppress verbose logging from OpenTelemetry and Azure Monitor libraries
SUPPRESSED_LOG_PACKAGES = [
    "azure.monitor.opentelemetry",
    "azure.core.pipeline.policies.http_logging_policy",
]

load_dotenv()

LOG_DIR = os.getenv("LOG_DIR", "/var/lib/pacs/logs")
os.makedirs(LOG_DIR, exist_ok=True)

for package_name in SUPPRESSED_LOG_PACKAGES:
    package_logger = logging.getLogger(package_name)
    package_logger.setLevel(logging.WARNING)


def configure_logging(
    name: str, max_log_size: int = DEFAULT_MAX_LOG_FILE_SIZE, backup_count: int = 5
) -> logging.Logger:
    """Configure logging for the application.

    Args:
        name: Optional file to write logs to. If None, logs will only go to the console.
        max_log_size: Maximum size of the log file before rotation occurs (default: 10 MB).
        backup_count: Number of backup log files to keep (default: 5).
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    format = os.getenv("LOG_FORMAT", DEFAULT_LOG_FORMAT)
    logging.basicConfig(format=format, level=level)
    configured_logger = logging.getLogger(name)
    configured_logger.setLevel(level)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(format))
    configured_logger.addHandler(console_handler)

    if os.getenv("LOG_TO_FILE", "true").lower() == "true":
        configured_logger.addHandler(log_rotation_handler(name, max_bytes=max_log_size, backup_count=backup_count))

    return configured_logger


def log_rotation_handler(name: str, max_bytes, backup_count) -> logging.Handler:
    """Create a rotating log handler.

    Args:
        name: The name of the logger, used to derive the file name to write logs to.
        max_bytes: The maximum size of the log file before rotation occurs.
        backup_count: The number of backup log files to keep.

    Returns:
        A configured logging.Handler instance.
    """
    from logging.handlers import RotatingFileHandler

    log_file_path = Path(LOG_DIR) / f"{name}.log"
    handler = RotatingFileHandler(log_file_path, maxBytes=max_bytes, backupCount=backup_count)
    handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
    return handler


def configure_telemetry(service_name: str | None = None) -> None:
    """Configure OpenTelemetry with Azure Monitor.

    If APPLICATIONINSIGHTS_CONNECTION_STRING is not set, this is a no-op,
    so local development works without any Azure configuration.

    Args:
        service_name: Identifies this service in Application Insights.
    """
    if not os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return

    if service_name:
        os.environ.setdefault("OTEL_SERVICE_NAME", service_name)

    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor()
    logger.info("Azure Monitor telemetry configured")
