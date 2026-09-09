# PACS Server

DICOM PACS (Picture Archiving and Communication System) server for receiving and storing medical images from breast screening modalities.

## Overview

The PACS server is a lightweight, production-ready DICOM storage solution that:

- Receives medical images via DICOM C-STORE protocol
- Stores the images using [hash-based directory structure](https://en.wikipedia.org/wiki/Content-addressable_storage)
- Indexes metadata in SQLite database
- Runs in a separate container alongside the [MWL Server](../mwl/README.md) (see [ADR-003](../adr/ADR-003_Separate_containers_for_PACS_and_MWL.md))

## Architecture

### Components

```text
┌─────────────────────────────────────────────────────────────────────┐
│                       PACS Server (Port 4244)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐   ┌─────────────┐   ┌──────────────┐              │
│  │   C-STORE    │──▶│   Resize    │──▶│   Compress   │              │
│  │   Handler    │   │  (Lanczos)  │   │  (JPEG 2000) │              │
│  └──────────────┘   └─────────────┘   └──────┬───────┘              │
│                                              │                      │
│                              ┌───────────────┴──────────────────┐   │
│                              │         Storage Layer            │   │
│                              ├──────────────────┬───────────────┤   │
│                              │  SQLite Database │  Filesystem   │   │
│                              └──────────────────┴───────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Accepted SOP Classes

The server only negotiates presentation contexts for the two mammography SOP classes sent by the Hologic Selenia Dimensions/3Dimensions:

- Digital mammography x-ray image storage – for presentation
- Digital mammography x-ray image storage – for processing

Other SOP classes (Secondary Capture, Breast Tomosynthesis, Dose SR, etc.) are rejected at association negotiation time so the modality knows not to send them.

### Image Processing Pipeline

When a C-STORE request arrives, the handler applies the following steps before writing to disk:

1. **Validate** — checks that required DICOM tags are present (`SOPInstanceUID`, `PatientID`, `StudyInstanceUID`, `SOPClassUID`) and that pixel data is consistent.
2. **Decompress** — if the image arrives in a compressed transfer syntax, it is decompressed before further processing.
3. **Resize** — if either dimension exceeds `DICOM_THUMBNAIL_SIZE` (default 400 px), the image is scaled down.
4. **Compress** — the pixel data is re-encoded as JPEG 2000 lossy at the configured compression ratio (`DICOM_COMPRESSION_RATIO`, default 15:1).
5. **Store** — the compressed DICOM file is written to the filesystem and indexed in the PACS database.

#### Why lossy compression and resizing?

Modalities send images in JPEG Lossless transfer syntax. The gateway PACS does not store clinical-grade images but rather reduced-resolution copies for display in Manage Breast Screening, where radiologists review appointment and worklist context rather than performing clinical reads. Full-resolution images remain on the BSU internal PACS. A 15:1 JPEG 2000 lossy compression ratio combined with a 400px resize reduces a typical mammography file from several hundred MB to tens of KB, which is appropriate for the thumbnail display use case and unproblematic for transferring via Azure Relay.

### Storage Structure

**Hash-based Directory Layout:**

```text
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
# Start both PACS and MWL servers
docker compose up -d

# Start only PACS server
docker compose up -d pacs

# View logs
docker compose logs -f pacs

# Stop servers
docker compose down

# Reset database and storage
docker compose down -v
```

## Configuration

Environment variables:

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `PACS_AET` | `SCREENING_PACS` | Application Entity Title |
| `PACS_PORT` | `4244` | DICOM service port |
| `PACS_STORAGE_PATH` | `/var/lib/pacs/storage` | Directory for DICOM files |
| `PACS_DB_PATH` | `/var/lib/pacs/pacs.db` | SQLite database path |
| `DICOM_THUMBNAIL_SIZE` | `400` | Max pixel dimension after resize (px) |
| `DICOM_COMPRESSION_RATIO` | `15` | JPEG 2000 lossy compression ratio |
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
