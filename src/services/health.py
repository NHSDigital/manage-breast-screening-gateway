"""Gateway health check

Answers the questions: are the MWL and PACS ports accepting connections,
are the gateway services running, is there disk headroom, and
what release is running.
"""

import os
import platform
import re
import shutil
import socket
import subprocess
import time

import config

PORT_CHECK_TIMEOUT_SECONDS = 0.5
DISK_MINIMUM_FREE_BYTES = 1 * 1024**3  # 1 GiB
DISK_MINIMUM_FREE_PERCENT = 5.0
# Service names must match the NSSM services installed by
# scripts/powershell/deploy.ps1.
SIBLING_SERVICES = ("Gateway-MWL", "Gateway-PACS", "Gateway-Upload")
SERVICE_QUERY_TIMEOUT_SECONDS = 2
_SERVICE_STATE_RUNNING = 4  # SERVICE_RUNNING in the Windows Service Control Manager

_STARTED_AT = time.time()


def _port_check(port: int) -> dict:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=PORT_CHECK_TIMEOUT_SECONDS):
            pass
        return {"ok": True}
    except OSError as e:
        return {"ok": False, "error": str(e)}


def _data_dir() -> str:
    return os.path.dirname(config.mwl_db_path()) or "."


def _disk_check() -> dict:
    try:
        usage = shutil.disk_usage(_data_dir())
        free_percent = (usage.free / usage.total) * 100 if usage.total else 0.0
        return {
            "ok": usage.free >= DISK_MINIMUM_FREE_BYTES and free_percent >= DISK_MINIMUM_FREE_PERCENT,
            "free_bytes": usage.free,
            "free_percent": round(free_percent, 1),
        }
    except OSError as e:
        return {"ok": False, "error": str(e)}


def _service_state(name: str) -> dict:
    """State of one Windows service, via `sc query`."""
    try:
        result = subprocess.run(
            ["sc", "query", name],
            capture_output=True,
            text=True,
            timeout=SERVICE_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": str(e)}

    match = re.search(r"STATE\s*:\s*(\d+)", result.stdout)
    if result.returncode != 0 or not match:
        return {"ok": False, "error": (result.stdout or result.stderr).strip()[:200]}
    state = int(match.group(1))
    return {"ok": state == _SERVICE_STATE_RUNNING, "state_code": state}


def _services_check() -> dict | None:
    """State of the services"""
    if platform.system() != "Windows":
        return None
    states = {name: _service_state(name) for name in SIBLING_SERVICES}
    return {"ok": all(s["ok"] for s in states.values()), "services": states}


def _release_version() -> str:
    """Release version parsed from this file's deployed path."""
    match = re.search(r"[/\\]releases[/\\]([^/\\]+)[/\\]", os.path.realpath(__file__))
    return match.group(1) if match else "unknown"


def collect_health() -> dict:
    """Collect the health payload for the relay `health` action."""
    checks = {
        "mwl_port": _port_check(config.mwl_port()),
        "pacs_port": _port_check(config.pacs_port()),
        "disk": _disk_check(),
    }

    services = _services_check()
    if services is not None:
        checks["services"] = services

    return {
        "healthy": all(check["ok"] for check in checks.values()),
        "version": _release_version(),
        "listener_uptime_seconds": int(time.time() - _STARTED_AT),
        "checks": checks,
    }
