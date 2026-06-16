import os
from unittest.mock import MagicMock, patch

import pytest

import telemetry


@pytest.fixture(autouse=True)
def setup_env(monkeypatch, tmp_dir):
    monkeypatch.setenv("LOG_DIR", f"{tmp_dir}/logs")


def test_configure_log_rotation_creates_rotating_handler(tmp_path):
    handler = telemetry.log_rotation_handler(
        "test_logger",
        max_bytes=1024,
        backup_count=3,
    )

    from logging.handlers import RotatingFileHandler

    assert isinstance(handler, RotatingFileHandler)
    assert handler.maxBytes == 1024
    assert handler.backupCount == 3
    assert handler.formatter._fmt == telemetry.DEFAULT_LOG_FORMAT
    assert handler.baseFilename.endswith("test_logger.log")


@patch("telemetry.log_rotation_handler")
@patch("logging.basicConfig")
def test_configure_logging(
    mock_basic_config,
    mock_configure_rotation,
    monkeypatch,
):
    mock_handler = MagicMock()
    mock_configure_rotation.return_value = mock_handler

    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_FORMAT", "%(levelname)s:%(message)s")

    logger = telemetry.configure_logging(
        "app_logger",
        max_log_size=2048,
        backup_count=2,
    )

    mock_basic_config.assert_called_once_with(
        level="DEBUG",
        format="%(levelname)s:%(message)s",
    )

    mock_configure_rotation.assert_called_once_with(
        "app_logger",
        max_bytes=2048,
        backup_count=2,
    )

    assert logger.name == "app_logger"


def test_configure_logging_adds_handler():
    handler = MagicMock()

    with patch.object(
        telemetry,
        "log_rotation_handler",
        return_value=handler,
    ):
        logger = telemetry.configure_logging("service_logger")

    assert handler in logger.handlers

    logger.removeHandler(handler)


def test_configure_telemetry_no_connection_string(monkeypatch):
    monkeypatch.delenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        raising=False,
    )

    with patch.dict("sys.modules", {}):
        telemetry.configure_telemetry("my-service")


def test_configure_telemetry_with_connection_string(monkeypatch):
    monkeypatch.setenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "InstrumentationKey=test",
    )

    mock_configure = MagicMock()

    with patch.dict(
        "sys.modules",
        {"azure.monitor.opentelemetry": MagicMock(configure_azure_monitor=mock_configure)},
    ):
        telemetry.configure_telemetry("my-service")

    assert os.environ["OTEL_SERVICE_NAME"] == "my-service"
    mock_configure.assert_called_once()


def test_configure_telemetry_does_not_override_existing_service_name(
    monkeypatch,
):
    monkeypatch.setenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "InstrumentationKey=test",
    )
    monkeypatch.setenv("OTEL_SERVICE_NAME", "existing-service")

    mock_configure = MagicMock()

    with patch.dict(
        "sys.modules",
        {"azure.monitor.opentelemetry": MagicMock(configure_azure_monitor=mock_configure)},
    ):
        telemetry.configure_telemetry("new-service")

    assert os.environ["OTEL_SERVICE_NAME"] == "existing-service"
    mock_configure.assert_called_once()
