import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.append(f"{Path(__file__).parent.parent}/src")


@pytest.fixture
def tmp_dir():
    return f"{Path(__file__).parent}/tmp"


@pytest.fixture(autouse=True)
def teardown(tmp_dir):
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)

    yield
    shutil.rmtree(tmp_dir)


class FakeWebSocket:
    """Async iterator + websocket mock."""

    def __init__(self, messages):
        self._messages = messages
        self.send = AsyncMock()
        self.recv = AsyncMock()

    def __aiter__(self):
        self._iter = iter(self._messages)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


@contextmanager
def fake_relay_contextmanager(relay_message, client_payload):
    relay_ws = FakeWebSocket([relay_message])
    client_ws = FakeWebSocket([])
    client_ws.recv.return_value = client_payload

    relay_cm = AsyncMock()
    relay_cm.__aenter__.return_value = relay_ws
    relay_cm.__aexit__.return_value = None

    client_cm = AsyncMock()
    client_cm.__aenter__.return_value = client_ws
    client_cm.__aexit__.return_value = None

    with patch("relay_listener.connect", side_effect=[relay_cm, client_cm]):
        yield client_ws


@pytest.fixture
def fake_relay():
    return fake_relay_contextmanager


@pytest.fixture
def listener_payload():
    return {
        "action_id": "action-12345",
        "action_type": "worklist.create_item",
        "parameters": {
            "worklist_item": {
                "participant": {
                    "nhs_number": "999123456",
                    "name": "SMITH^JANE",
                    "birth_date": "19900202",
                    "sex": "F",
                },
                "scheduled": {
                    "date": "20240615",
                    "time": "101500",
                },
                "procedure": {
                    "modality": "MG",
                    "study_description": "MAMMOGRAPHY",
                },
                "accession_number": "ACC999999",
            }
        },
    }
