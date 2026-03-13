import logging
import os

logger = logging.getLogger(__name__)


def configure_telemetry() -> None:
    """Configure OpenTelemetry with Azure Monitor.

    If APPLICATIONINSIGHTS_CONNECTION_STRING is not set, this is a no-op,
    so local development works without any Azure configuration.
    """
    if not os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return

    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor()
    logger.info("Azure Monitor telemetry configured")
