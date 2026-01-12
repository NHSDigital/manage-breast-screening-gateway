# NHS Manage Breast Screening Gateway

NHS Digital Breast Screening Service - Gateway services for on-premises DICOM modalities

## Overview

This service provides a gateway between on-premises DICOM modalities (mammography systems) and the cloud-based [Manage Breast Screening](https://github.com/NHSDigital/dtos-manage-breast-screening) platform.

## Features

- DICOM Worklist (C-FIND) support
- DICOM Storage (C-STORE)
- MPPS (Modality Performed Procedure Step) tracking
- Secure communication via Azure Relay
- Image thumbnail generation

## Prerequisites

- [Python](https://www.python.org/)
- [Docker](https://www.docker.com/) container runtime or a compatible tool, e.g. [Podman](https://podman.io/),
- [asdf](https://asdf-vm.com/)
- [GNU make](https://www.gnu.org/software/make/) 3.82 or later,

## Quick Start

```bash

git clone git@github.com:NHSDigital/manage-breast-screening-gateway.git
cd manage-breast-screening-gateway

# 2. Set up development environment
make config

# 3. Run tests
make test
```

## Development

### Available Make Commands

```bash
make help          # Show all available commands
make config        # Set up development environment
make test          # Run all tests (unit + lint)
make test-unit     # Run unit tests only
make test-lint     # Run linting only
make clean         # Clean up build artifacts
make githooks-run  # Run pre-commit hooks manually
```

### Project Structure

```
manage-breast-screening-gateway/
├── docs/                      # Documentation
│   ├── adr/                   # Architecture Decision Records
│   ├── developer-guides/      # Developer documentation
│   └── user-guides/           # User documentation
├── scripts/                   # Build and utility scripts
├── src/                       # Source code
├── tests/                     # Test files
├── .github/                   # GitHub Actions CI/CD
├── Makefile                   # Development commands
├── pyproject.toml             # Python project configuration
└── README.md                  # This file
```

### Running Tests

```bash
# All tests
make test

# Unit tests
make test-unit

# Linting (ruff + pyright)
make test-lint
# Verbose output

make test-unit ARGS="-v"
```

### Code Quality

Pre-commit hooks run automatically on commit:

- **Secrets scanning** (gitleaks)
- **Code formatting** (ruff format)
- **Linting** (ruff check)

Run manually:

```bash
make githooks-run
```

## Architecture

This gateway implements a lightweight DICOM service architecture:

1. **DICOM Worklist Server** - Provides scheduled procedure information to modalities
2. **DICOM PACS Server** - Receives and stores medical images ([docs](docs/pacs/README.md))
3. **Event Processing** - Processes MPPS status updates and image metadata
4. **Azure Relay Communication** - Bidirectional communication with cloud service

### PACS Server

The PACS server provides C-STORE functionality for receiving medical images:
- Hash-based storage for scalability
- SQLite metadata indexing
- Thread-safe concurrent access
- Docker containerized deployment

See [PACS documentation](docs/pacs/README.md) for detailed information.

### Relay Listener

The Relay Listener handles incoming messages from the cloud service via Azure Relay:
- Listens on configured Hybrid Connection
- Processes worklist actions (e.g., create worklist item)

See [Relay Listener documentation](docs/relay-listener/README.md) for details.

## Testing

This project uses:

- **pytest** for unit testing
- **pytest-cov** for coverage reporting
- **ruff** for linting and formatting
- **pyright** for static type checking

## Contributing

- Make sure you have `pre-commit` running so that pre-commit hooks run automatically when you commit - this should have been set up automatically when you ran `make config`.
- Consider switching on format-on-save in your editor (e.g. [Black](https://github.com/psf/black) for python)
- (Internal contributions only) contact the `#screening-manage` team on slack with any questions

### More documentation

Explore [the docs directory](docs).

## Licence

Unless stated otherwise, the codebase is released under the MIT License. This covers both the codebase and any sample code in the documentation. See [LICENCE.md](./LICENCE.md).

Any HTML or Markdown documentation is [© Crown Copyright](https://www.nationalarchives.gov.uk/information-management/re-using-public-sector-information/uk-government-licensing-framework/crown-copyright/) and available under the terms of the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

## Support

For issues or questions:

- Create a GitHub issue
- Contact the NHS Digital Breast Screening team
