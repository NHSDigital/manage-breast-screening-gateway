# MWL Server

DICOM [Modality Worklist (MWL)](https://dicom.nema.org/medical/dicom/current/output/html/part04.html#chapter_K) server for managing scheduled breast screening appointments and providing worklist information to imaging modalities.

## Overview

The MWL server is a lightweight, production-ready DICOM worklist solution that:

- Provides scheduled procedure information via [DICOM C-FIND](https://dicom.nema.org/medical/dicom/current/output/html/part04.html#chapter_C) protocol
- Stores worklist items in SQLite database
- Supports filtering by modality, date, and patient ID
- Resets the worklist on a schedule, backing up the database before clearing it
- Runs in a separate container alongside the [PACS Server](../pacs/README.md)

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    MWL Server (Port 4243)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────┐   │
│  │   C-FIND     │─────▶│   Storage    │─────▶│ SQLite   │◀──┼──────────────────┐
│  │   Handler    │      │   Layer      │      │ Database │   │                  │
│  └──────────────┘      └──────────────┘      └──────────┘   │                  │
│         │                      ▲                            │                  │
│         │                      │                            │        backup + clear (cron)
│         └──────────────────────┘                            │                  │
│         Query & Response                                    │                  │
└─────────────────────────────────────────────────────────────┘                  │
           ▲                          ▲                                   ┌──────┴─────────┐
           │                          │                                   │ Reset Scheduler│
    ┌──────┴──────┐           ┌───────┴────────┐                          └────────────────┘
    │  Modality   │           │ Relay Listener │
    │  (SCU)      │           │ (Populates DB) │
    └─────────────┘           └────────────────┘
```

### Workflow

1. **Worklist Creation**: Relay listener receives appointments from Manage Breast Screening and creates worklist items
2. **Worklist Query**: Modality sends C-FIND request to MWL server
3. **Filtering**: MWL server filters by modality, date, patient ID, status
4. **Response**: Server returns matching worklist items to modality
5. **Status Updates**: C-STORE receipt transitions items from `SCHEDULED` to `IN PROGRESS`; [MPPS](https://dicom.nema.org/medical/dicom/current/output/html/part04.html#chapter_F) transitions items to `COMPLETED` or `DISCONTINUED`
6. **Reset**: Reset scheduler backs up and clears the database on a configurable schedule

## Running the MWL Server

The MWL server runs in a separate container:

```bash
# Start all services
docker compose up -d

# Start only the MWL server and reset scheduler
docker compose up -d mwl reset

# View MWL server logs
docker compose logs -f mwl

# View reset scheduler logs
docker compose logs -f reset

# Stop all services
docker compose down
```

## Configuration

### MWL server

| Variable | Default | Description |
|----------|---------|-------------|
| `MWL_AET` | `MWL_SCP` | Application Entity Title |
| `MWL_PORT` | `4243` | DICOM service port |
| `MWL_DB_PATH` | `/var/lib/pacs/worklist.db` | SQLite database path |
| `LOG_LEVEL` | `INFO` | Logging level |

### Reset scheduler

| Variable | Default | Description |
|----------|---------|-------------|
| `MWL_DB_PATH` | `/var/lib/pacs/worklist.db` | SQLite database path |
| `BACKUP_PATH` | `/var/lib/pacs/backups` | Directory for database backups |
| `MWL_RESET_SCHEDULE` | `0 2 * * *` | Cron expression for reset schedule (UTC) |
| `LOG_LEVEL` | `INFO` | Logging level |

The `MWL_RESET_SCHEDULE` value is a standard cron expression. Examples:

| Expression | Schedule |
|------------|----------|
| `0 2 * * *` | Daily at 02:00 UTC (default) |
| `0 2 * * 1` | Every Monday at 02:00 UTC |
| `0 2 1 * *` | First day of each month at 02:00 UTC |

## Example query

```python
from pynetdicom import AE, QueryRetrievePresentationContexts
from pydicom import Dataset

ae = AE()
ae.requested_contexts = QueryRetrievePresentationContexts

# Create query dataset
ds = Dataset()
ds.PatientID = '9876543210'
ds.PatientName = ''
ds.AccessionNumber = ''

# Scheduled procedure step query
sps = Dataset()
sps.Modality = 'MG'
sps.ScheduledProcedureStepStartDate = '20260108'
ds.ScheduledProcedureStepSequence = [sps]

# Send C-FIND with Worklist Information Model ('W')
assoc = ae.associate('localhost', 4243, ae_title='MWL_SCP')
responses = assoc.send_c_find(ds, query_model='W')
for (status, identifier) in responses:
    if status.Status in (0xFF00, 0xFF01):
        print(f"Found: {identifier.PatientName}")
assoc.release()
```

## Verification

Check worklist items:

```bash
docker compose exec gateway sqlite3 /var/lib/pacs/worklist.db \
  "SELECT accession_number, patient_name, scheduled_date, status FROM worklist_items;"
```

Add test worklist item:

```bash
docker compose exec gateway sqlite3 /var/lib/pacs/worklist.db <<EOF
INSERT INTO worklist_items (
    accession_number, patient_id, patient_name, patient_birth_date,
    scheduled_date, scheduled_time, modality, study_description
) VALUES (
    'ACC001', '9876543210', 'TEST^PATIENT', '19800101',
    '20260108', '100000', 'MG', 'Bilateral Screening Mammogram'
);
EOF
```

## Integration testing

**Running integration tests:**

```bash
uv run pytest tests/integration/test_c_find_returns_worklist_items.py -v
uv run pytest tests/integration/test_request_cfind_on_worklist.py -v
```

## Multi-container architecture

The MWL-related services run in separate containers. See [ADR-003: Separate containers for PACS and MWL](../adr/ADR-003_Separate_containers_for_PACS_and_MWL.md) and [ADR-004: Daily backup and reset of the MWL database](../adr/ADR-004_MWL_Daily_Backup_And_Reset.md) for the architectural decisions.

**Docker Compose services:**

```yaml
services:
  mwl:
    container_name: mwl-server
    command: ["uv", "run", "python", "-m", "mwl_main"]
    ports:
      - "4243:4243"

  reset:
    container_name: mwl-reset
    command: ["uv", "run", "python", "-m", "reset_main"]
```

**Worklist item status transitions:**

```
SCHEDULED ──(first C-STORE)──▶ IN PROGRESS ──(MPPS N-SET)──▶ COMPLETED
                                     │
                                     └────────(MPPS N-SET)──▶ DISCONTINUED
```
