# PACS Server

DICOM PACS (Picture Archiving and Communication System) server for receiving and storing medical images from breast screening modalities.

## Overview

The PACS server is a lightweight, production-ready DICOM storage solution that:
- Receives medical images via DICOM C-STORE protocol
- Stores the images using hash-based directory structure
- Indexes metadata in SQLite database
- Runs alongside the [MWL Server](../mwl/README.md) in the same Docker container (see [ADR-003](../adr/ADR-003_Multi_threaded_PACS_MWL_server.md))

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    PACS Server (Port 4244)                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────┐   │
│  │   C-STORE    │─────▶│   Storage    │─────▶│ SQLite   │   │
│  │   Handler    │      │   Layer      │      │ Database │   │
│  └──────────────┘      └──────────────┘      └──────────┘   │
│         │                      │                            │
│         │                      ▼                            │
│         │              ┌──────────────┐                     │
│         └─────────────▶│  Filesystem  │                     │
│                        └──────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

### Storage Structure

**Hash-based Directory Layout:**
```
storage/
├── b2/
│   └── 51/
│       └── b2512f75cdde020b.dcm
├── 31/
│   └── 4b/
│       └── 314bcc75263d340e.dcm
└── 8e/
    └── c3/
        └── 8ec35a2d6ab517e2.dcm
```

Each file is stored using SHA256 hash of its SOP Instance UID:
- First 2 characters → Level 1 directory
- Characters 3-4 → Level 2 directory
- First 16 characters + `.dcm` → Filename

### Database Schema

Simplified schema with essential fields:

```sql
CREATE TABLE stored_instances (
    sop_instance_uid TEXT PRIMARY KEY,
    storage_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    storage_hash TEXT NOT NULL,
    patient_id TEXT,
    patient_name TEXT,
    accession_number TEXT,
    source_aet TEXT,
    status TEXT DEFAULT 'STORED',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## Running the PACS Server

```bash
# Start the server
docker compose up -d

# View logs
docker compose logs -f pacs

# Stop the server
docker compose down

# Reset database and storage
docker compose down -v
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PACS_AET` | `SCREENING_PACS` | Application Entity Title |
| `PACS_PORT` | `4244` | DICOM service port |
| `PACS_STORAGE_PATH` | `/var/lib/pacs/storage` | Directory for DICOM files |
| `PACS_DB_PATH` | `/var/lib/pacs/pacs.db` | SQLite database path |
| `LOG_LEVEL` | `INFO` | Logging level |

## Verification

The PACS server can be manually tested using a modality emulator or a `pynetdicom` script.

Check stored images:

```bash
docker compose exec pacs uv run python scripts/verify_storage.py
```

## Integration Testing

Integration tests run the PACS server in a separate Python thread and send real DICOM data via C-STORE. See [ADR-002: Testing Strategy](../adr/ADR-002_Testing_strategy.md).

**Running integration tests:**

```bash
# Run all integration tests
make test-integration

# Run specific test
uv run pytest tests/integration/test_send_c_store_to_gateway.py -v
```

## Security

**Current Implementation:**
- No authentication (intended for internal network)
- No encryption (use VPN/private network)
- File integrity via SHA256 hashes

**Future Considerations:**
- TLS support for encrypted transport
- Application-level authentication
