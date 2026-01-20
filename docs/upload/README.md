# Upload Service

Background service that uploads stored DICOM images to the [Manage Breast Screening](https://github.com/NHSDigital/dtos-manage-breast-screening) cloud platform.

## Overview

The upload service:

- Polls the PACS database for stored images pending upload
- Uploads images to the Manage API as multipart form data
- Links images to appointments via the `X-Source-Message-ID` header
- Runs alongside the [PACS Server](../pacs/README.md) and [MWL Server](../mwl/README.md)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Upload Service                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────┐   │
│  │   Upload     │─────▶│   Upload     │─────▶│  DICOM   │   │
│  │   Listener   │      │   Processor  │      │  Uploader│   │
│  └──────────────┘      └──────────────┘      └──────────┘   │
│         │                     │                    │        │
│         │                     ▼                    │        │
│         │              ┌──────────────┐            │        │
│         │              │ PACS Storage │            │        │
│         │              │ (files + DB) │            │        │
│         │              └──────────────┘            │        │
│         │                     │                    │        │
│         │                     ▼                    ▼        │
│         │              ┌──────────────┐     ┌────────────┐  │
│         │              │ MWL Storage  │     │ Manage API │  │
│         │              │ (worklist DB)│     │ (HTTP)     │  │
│         └──────────────┴──────────────┘     └────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Workflow

1. **Poll**: Listener polls PACS database every N seconds for pending uploads
2. **Read**: Processor reads DICOM file from hash-based storage
3. **Lookup**: Processor looks up `source_message_id` from MWL database via accession number
4. **Upload**: Uploader sends multipart POST to cloud API with `X-Source-Message-ID` header
5. **Update**: Processor updates upload status in PACS database (COMPLETE or retry)

### Retry Behaviour

- Failed uploads return to `PENDING` status for retry
- After max retries (default 3), status becomes `FAILED`
- Exponential backoff between batches when failures occur
- Backoff starts at 1s, doubles each failure, caps at 60s

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLOUD_API_ENDPOINT` | `http://localhost:8000/api/dicom/upload/` | Manage API upload endpoint |
| `PACS_DB_PATH` | `/var/lib/pacs/pacs.db` | PACS SQLite database path |
| `PACS_STORAGE_PATH` | `/var/lib/pacs/storage` | PACS file storage path |
| `MWL_DB_PATH` | `/var/lib/pacs/worklist.db` | MWL SQLite database path |
| `UPLOAD_POLL_INTERVAL` | `2` | Seconds between polling cycles |
| `UPLOAD_BATCH_SIZE` | `10` | Max uploads per cycle |
| `MAX_UPLOAD_RETRIES` | `3` | Retry attempts before permanent failure |
| `LOG_LEVEL` | `INFO` | Logging level |
