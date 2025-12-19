# Getting Started

This guide will help you set up your development environment for the NHS Manage Breast Screening Gateway.

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.14+** (or use asdf to install the correct version)
- **asdf** - Version manager for multiple runtime versions
- **GNU Make** - Build automation tool (3.82+)
- **Git** - Version control

## Quick Start

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd manage-breast-screening-gateway
   ```

2. **Set up the environment**:
   ```bash
   make config
   ```

   This command will:
   - Install tools from `.tool-versions` (Python, uv, pre-commit, vale, gitleaks)
   - Install Python dependencies via uv
   - Set up pre-commit hooks

3. **Run tests**:
   ```bash
   make test
   ```

4. **Run linting**:
   ```bash
   make test-lint
   ```

## Development Workflow

### Running Tests

```bash
# Run all tests
make test

# Run only unit tests
make test-unit

# Run with specific pytest args
make test-unit ARGS="-v -k test_specific_function"

# Run with coverage
make test-unit ARGS="--cov-report=html"
```

### Linting and Formatting

```bash
# Run all linting (ruff + pyright)
make test-lint

# Auto-fix ruff issues
uv run ruff check --fix .

# Format code
uv run ruff format .
```

### Pre-commit Hooks

Pre-commit hooks run automatically on `git commit`. To run them manually:

```bash
make githooks-run
```

To skip hooks temporarily (not recommended):
```bash
git commit --no-verify
```

### Adding Dependencies

```bash
# Add a production dependency
uv add <package-name>

# Add a development dependency
uv add --dev <package-name>

# Update dependencies
uv sync
```

## Project Structure

```
manage-breast-screening-gateway/
├── docs/                      # Documentation
│   ├── adr/                   # Architecture Decision Records
│   ├── developer-guides/      # Developer documentation
│   └── user-guides/           # User documentation
├── scripts/                   # Build and utility scripts
│   ├── config/                # Tool configurations
│   └── githooks/              # Pre-commit hook scripts
├── src/                       # Source code (your code goes here)
├── tests/                     # Test files
├── .github/                   # GitHub Actions workflows
├── Makefile                   # Development commands
└── pyproject.toml             # Python project configuration
```

## Useful Commands

```bash
make help          # Show all available commands
make clean         # Clean up build artifacts
make config        # Re-run environment setup
```

## Troubleshooting

### uv not found

If `make config` fails with `uv: command not found`:

```bash
# Install uv manually
pip install uv==0.9.7

# Or using asdf
asdf install uv 0.9.7
```

### Pre-commit hooks failing

If hooks are failing:

```bash
# Update pre-commit
pip install --upgrade pre-commit

# Re-install hooks
pre-commit install -c scripts/config/pre-commit.yaml
```

### Python version issues

Ensure you're using Python 3.14+:

```bash
python --version

# If wrong version, install via asdf
asdf install python 3.14.0
asdf global python 3.14.0
```

## Next Steps

- Read [Testing.md](./Testing.md) for testing guidelines
- Read [Makefile_Usage.md](./Makefile_Usage.md) for detailed make command documentation
- See [docs/adr/](../adr/) for architectural decisions
