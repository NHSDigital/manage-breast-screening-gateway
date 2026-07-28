import inspect
import json
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from pydicom import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian
from pynetdicom.sop_class import (
    DigitalMammographyXRayImageStorageForPresentation,
)

sys.path.append(f"{Path(__file__).parent.parent}/src")

READABLE_TEST_OUTPUT = not any("neotest" in arg for arg in sys.argv)


def pytest_html_report_title(report):
    report.title = "Rubie Gateway Tests"


def _readable_test_name(item):
    """
    Use the test's docstring (first line) as its name in the report. Every
    test is expected to have a docstring; falls back to the default node id
    if one is missing.
    """
    test_fn = getattr(item, "obj", None)
    docstring = inspect.getdoc(test_fn) if test_fn else None
    if not docstring:
        return None

    # First non-empty line, whitespace collapsed — docstrings are often
    # multi-line and indented, which would render badly as a node id.
    base = next((line.strip() for line in docstring.splitlines() if line.strip()), "")
    if not base:
        return None

    # Keep parametrised cases distinct (they share one docstring).
    param_id = getattr(getattr(item, "callspec", None), "id", None)
    return f"{base} [{param_id}]" if param_id else base


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Use the test's docstring as its name in the report."""
    outcome = yield
    report = outcome.get_result()

    readable_name = _readable_test_name(item)
    if readable_name and READABLE_TEST_OUTPUT:
        report.nodeid = readable_name


@pytest.fixture(autouse=True)
def mock_azure_credential():
    mock = MagicMock()
    mock.get_token.return_value.token = "test-token"
    with (
        patch("relay_listener.DefaultAzureCredential", return_value=mock),
        patch("relay_listener.ManagedIdentityCredential", return_value=mock),
    ):
        yield mock


@pytest.fixture
def tmp_dir():
    return Path(__file__).parent / "tmp"


@pytest.fixture(autouse=True)
def teardown(tmp_dir):
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)

    yield
    shutil.rmtree(tmp_dir)


# DICOM test fixtures
@pytest.fixture
def dicom_file_meta():
    """Create standard DICOM file meta information."""
    file_meta = FileMetaDataset()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.MediaStorageSOPClassUID = DigitalMammographyXRayImageStorageForPresentation
    return file_meta


@pytest.fixture
def dataset_with_pixels(dicom_file_meta):
    """Create a DICOM dataset with pixel data (256x256, 16-bit)."""
    ds = Dataset()
    ds.Rows = 256
    ds.Columns = 256
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = np.zeros((256, 256), dtype=np.uint16).tobytes()
    ds.file_meta = dicom_file_meta
    return ds


@pytest.fixture
def dataset_without_pixels(dicom_file_meta):
    """Create a DICOM dataset without pixel data."""
    ds = Dataset()
    ds.PatientID = "123456"
    ds.PatientName = "TEST^PATIENT"
    ds.file_meta = dicom_file_meta
    return ds


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
    import relay_listener

    relay_ws = FakeWebSocket([])
    relay_ws.recv.return_value = relay_message
    client_ws = FakeWebSocket([])
    client_ws.recv.return_value = client_payload

    relay_cm = AsyncMock()
    relay_cm.__aenter__.return_value = relay_ws
    relay_cm.__aexit__.return_value = None

    client_cm = AsyncMock()
    client_cm.__aenter__.return_value = client_ws
    client_cm.__aexit__.return_value = None

    async def fake_listen(self):
        async with relay_listener.connect("wss://relay", compression=None) as ws:
            relay_data = await ws.recv()
            data = json.loads(relay_data)

            if "accept" not in data:
                return

            accept_url = data["accept"]["address"]
            async with relay_listener.connect(
                accept_url,
                compression=None,
            ) as accept_ws:
                client_message = await accept_ws.recv()
                payload = json.loads(client_message)
                response = self.process_action(payload)
                await accept_ws.send(json.dumps(response))

    with (
        patch("relay_listener.connect", side_effect=[relay_cm, client_cm]),
        patch.object(relay_listener.RelayListener, "listen", fake_listen),
    ):
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
