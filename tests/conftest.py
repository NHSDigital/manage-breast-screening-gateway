import shutil
import sys
from pathlib import Path

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


def assert_sql_equal(expected: str, actual: str):
    def normalize(sql: str) -> str:
        return "\n".join(line.strip() for line in sql.strip().splitlines() if line.strip())

    assert normalize(expected) == normalize(actual), (
        f"SQL statements do not match. Expected:\n{normalize(expected)}\n\nActual:\n{normalize(actual)}"
    )
