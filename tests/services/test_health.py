"""Tests for the on-VM health collection behind the relay `health` action."""

import socket

from services import health
from services.health import (
    _port_check,
    _release_version,
    _service_state,
    _services_check,
    collect_health,
)


class TestPortCheck:
    def test_reports_ok_for_listening_port(self):
        """Health: port check ok when something is listening."""
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        try:
            assert _port_check(port) == {"ok": True}
        finally:
            server.close()

    def test_reports_error_for_closed_port(self):
        """Health: port check reports error when nothing is listening."""
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.close()  # bound then released: guaranteed unused

        result = _port_check(port)

        assert result["ok"] is False
        assert "error" in result


class TestDiskCheck:
    def test_reports_usage_for_data_dir(self, tmp_path, monkeypatch):
        """Health: disk check reports free space for the data directory."""
        monkeypatch.setenv("MWL_DB_PATH", str(tmp_path / "worklist.db"))

        result = health._disk_check()

        assert result["free_bytes"] > 0
        assert 0 <= result["free_percent"] <= 100


class TestServicesCheck:
    SC_RUNNING = """
SERVICE_NAME: Gateway-MWL
        TYPE               : 10  WIN32_OWN_PROCESS
        STATE              : 4  RUNNING
"""
    SC_STOPPED = """
SERVICE_NAME: Gateway-Upload
        TYPE               : 10  WIN32_OWN_PROCESS
        STATE              : 1  STOPPED
"""

    def _fake_run(self, stdout, returncode=0):
        import subprocess

        return subprocess.CompletedProcess(args=["sc"], returncode=returncode, stdout=stdout, stderr="")

    def test_running_service_reports_ok(self, monkeypatch):
        """Health: a running Windows service reports ok."""
        monkeypatch.setattr(health.subprocess, "run", lambda *a, **k: self._fake_run(self.SC_RUNNING))

        assert _service_state("Gateway-MWL") == {"ok": True, "state_code": 4}

    def test_stopped_service_reports_not_ok(self, monkeypatch):
        """Health: a stopped Windows service reports not ok with its state code."""
        monkeypatch.setattr(health.subprocess, "run", lambda *a, **k: self._fake_run(self.SC_STOPPED))

        assert _service_state("Gateway-Upload") == {"ok": False, "state_code": 1}

    def test_unknown_service_reports_error(self, monkeypatch):
        """Health: an unknown service reports an error."""
        monkeypatch.setattr(
            health.subprocess,
            "run",
            lambda *a, **k: self._fake_run("The specified service does not exist.", returncode=1060),
        )

        result = _service_state("Gateway-Nope")

        assert result["ok"] is False
        assert "error" in result

    def test_omitted_off_windows(self, monkeypatch):
        """Health: services check is omitted on non-Windows platforms."""
        monkeypatch.setattr(health.platform, "system", lambda: "Linux")

        assert _services_check() is None

    def test_aggregates_sibling_services_on_windows(self, monkeypatch):
        """Health: services check aggregates all sibling services on Windows."""
        monkeypatch.setattr(health.platform, "system", lambda: "Windows")
        monkeypatch.setattr(health.subprocess, "run", lambda *a, **k: self._fake_run(self.SC_RUNNING))

        result = _services_check()

        assert result["ok"] is True
        assert set(result["services"]) == {"Gateway-MWL", "Gateway-PACS", "Gateway-Upload"}


class TestReleaseVersion:
    def test_parses_version_from_releases_path(self, monkeypatch):
        """Health: version parsed from a releases/<version>/ path."""
        monkeypatch.setattr(
            "os.path.realpath",
            lambda _: r"C:\Program Files\NHS\ManageBreastScreeningGateway\releases\v1.7.0\src\services\health.py",
        )
        assert _release_version() == "v1.7.0"


class TestCollectHealth:
    def test_returns_full_schema(self, tmp_path, monkeypatch):
        """Health: collected payload contains the contract schema."""
        monkeypatch.setenv("MWL_DB_PATH", str(tmp_path / "worklist.db"))

        result = collect_health()

        assert set(result) == {"healthy", "version", "listener_uptime_seconds", "checks"}
        assert {"mwl_port", "pacs_port", "disk"} <= set(result["checks"])
        assert isinstance(result["healthy"], bool)
        assert result["listener_uptime_seconds"] >= 0

    def test_unhealthy_when_any_check_fails(self, tmp_path, monkeypatch):
        """Health: aggregate healthy is false when a check fails."""
        monkeypatch.setenv("MWL_DB_PATH", str(tmp_path / "worklist.db"))
        # Nothing listens on the default dev ports in the test environment,
        # so the port checks fail and the aggregate must reflect that.
        result = collect_health()

        if not result["checks"]["mwl_port"]["ok"]:
            assert result["healthy"] is False
