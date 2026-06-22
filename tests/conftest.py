import inspect
import re
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


def pytest_html_report_title(report):
    report.title = "Rubie Gateway Tests"


# Domain acronyms that should render in their conventional form rather than
# being naively title-cased from the test function name.
_ACRONYMS = {
    "cfind": "C-FIND",
    "cstore": "C-STORE",
    "cecho": "C-ECHO",
    "ncreate": "N-CREATE",
    "nset": "N-SET",
    "mwl": "MWL",
    "mpps": "MPPS",
    "pacs": "PACS",
    "dicom": "DICOM",
    "sop": "SOP",
    "uid": "UID",
    "ae": "AE",
    "aet": "AE title",
    "sas": "SAS",
    "jpeg2000": "JPEG 2000",
    "sqlite": "SQLite",
}


# Two-token DICOM operations, so they can be recognised as a single acronym.
_DICOM_OPS = {
    ("c", "store"): "C-STORE",
    ("c", "find"): "C-FIND",
    ("c", "echo"): "C-ECHO",
    ("n", "set"): "N-SET",
    ("n", "create"): "N-CREATE",
}

# Method names whose humanised form says nothing without the class context
# (the meaning lives in the test class, e.g. ``call`` in ``TestCFind``).
_GENERIC_FIRST_WORDS = {
    "call",
    "init",
    "start",
    "stop",
    "str",
    "repr",
    "setup",
    "run",
    "success",
    "failure",
    "handle",
    "handles",
    "update",
    "upload",
}


def _apply_acronyms(words):
    return [_ACRONYMS.get(word.lower(), word) for word in words]


def _humanise_test_name(func_name):
    """
    Turn a test function name into a readable phrase, e.g.
    ``test_cfind_filters_by_accession_number`` -> "C-FIND filters by
    accession number".
    """
    name = func_name.removeprefix("test_")
    for split, joined in (
        ("c_store", "cstore"),
        ("c_find", "cfind"),
        ("c_echo", "cecho"),
        ("n_set", "nset"),
        ("n_create", "ncreate"),
    ):
        name = name.replace(split, joined)
    phrase = " ".join(_apply_acronyms(name.split("_")))
    return phrase[:1].upper() + phrase[1:] if phrase else func_name


def _humanise_class_name(cls_name):
    """
    Turn a test class name into a readable component label, e.g.
    ``TestCFind`` -> "C-FIND", ``TestMWLServer`` -> "MWL server".
    """
    name = cls_name.removeprefix("Test")
    tokens = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|\d+", name)

    out, i = [], 0
    while i < len(tokens):
        pair = (tokens[i].lower(), tokens[i + 1].lower()) if i + 1 < len(tokens) else None
        if pair in _DICOM_OPS:
            out.append(_DICOM_OPS[pair])
            i += 2
            continue
        token = tokens[i]
        out.append(_ACRONYMS.get(token.lower(), token if token.isupper() else token.lower()))
        i += 1

    phrase = " ".join(out)
    return phrase[:1].upper() + phrase[1:] if phrase else cls_name


def _readable_test_name(item):
    """
    Build a human-readable name for the test report. Prefers the test's
    docstring (first line). Otherwise humanises the function name, and — when
    that name is too generic to stand alone (e.g. ``test_call``) — prefixes
    the humanised test-class name for context. Means every row reads well
    without a docstring on every test.
    """
    test_fn = getattr(item, "obj", None)
    docstring = inspect.getdoc(test_fn) if test_fn else None

    if docstring:
        # First non-empty line, whitespace collapsed — docstrings are often
        # multi-line and indented, which would render badly as a node id.
        base = next((line.strip() for line in docstring.splitlines() if line.strip()), "")
    else:
        base = ""

    if not base:
        method = _humanise_test_name(getattr(item, "originalname", None) or item.name)
        words = method.split()
        is_generic = not words or words[0].lower() in _GENERIC_FIRST_WORDS or len(words) <= 2
        cls = getattr(item, "cls", None)
        if is_generic and cls is not None:
            base = f"{_humanise_class_name(cls.__name__)}: {method}"
        else:
            base = method

    # Keep parametrised cases distinct (they share one name).
    param_id = getattr(getattr(item, "callspec", None), "id", None)
    return f"{base} [{param_id}]" if param_id else base


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Use a readable docstring/humanised name as the test's name in the report."""
    outcome = yield
    report = outcome.get_result()

    readable_name = _readable_test_name(item)
    if readable_name:
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
    return f"{Path(__file__).parent}/tmp"


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
