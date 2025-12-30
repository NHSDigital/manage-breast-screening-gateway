import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../src")


@pytest.fixture
def tmp_dir():
    return f"{os.path.dirname(os.path.realpath(__file__))}/tmp"


@pytest.fixture(autouse=True)
def teardown(tmp_dir):
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)

    yield
    shutil.rmtree(tmp_dir)
