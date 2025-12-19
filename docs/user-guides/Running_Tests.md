# Running Tests

## Quick Start

Run all tests:
```bash
make test
```

This runs:
- Unit tests (pytest)
- Linting (ruff + pyright)

## Unit Tests Only

```bash
make test-unit
```

Options:
```bash
# Verbose output
make test-unit ARGS="-v"

# Run specific test file
make test-unit ARGS="tests/test_example.py"

# Run specific test
make test-unit ARGS="-k test_function_name"

# Generate HTML coverage report
make test-unit ARGS="--cov-report=html"
# View at: htmlcov/index.html
```

## Linting Only

```bash
make test-lint
```

This checks:
- Ruff linting (code quality)
- Ruff formatting (code style)
- Pyright (type checking)

## Writing Tests

### Test File Location
Place tests in `tests/` directory:
```
tests/
├── test_module_one.py
├── test_module_two.py
└── conftest.py           # Shared fixtures
```

### Test Example

```python
# tests/test_example.py
import pytest

def test_addition():
    assert 1 + 1 == 2

@pytest.mark.integration
def test_database_connection():
    # Integration test
    pass
```

### Test Markers

Mark tests by type:
```python
@pytest.mark.unit          # Unit test (default)
@pytest.mark.integration   # Integration test
```

## Coverage Reports

View coverage after running tests:
```bash
# Terminal summary
make test-unit

# HTML report
make test-unit ARGS="--cov-report=html"
open htmlcov/index.html
```

Coverage configuration is in `pyproject.toml` under `[tool.coverage]`.
