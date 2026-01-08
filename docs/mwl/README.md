# MWL Server

DICOM Modality Worklist (MWL) server for managing scheduled breast screening appointments and providing worklist information to imaging modalities.

## Overview

The MWL server is a lightweight, production-ready DICOM worklist solution that:

- Provides scheduled procedure information via DICOM C-FIND protocol
- Stores worklist items in SQLite database
- Supports filtering by modality, date, and patient ID
- Runs in a separate container alongside the [PACS Server](../pacs/README.md)

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    MWL Server (Port 4243)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────┐   │
│  │   C-FIND     │─────▶│   Storage    │─────▶│ SQLite   │   │
│  │   Handler    │      │   Layer      │      │ Database │   │
│  └──────────────┘      └──────────────┘      └──────────┘   │
│         │                      ▲                            │
│         │                      │                            │
│         └──────────────────────┘                            │
│         Query & Response                                    │
└─────────────────────────────────────────────────────────────┘
           ▲                                     ▲
           │                                     │
    ┌──────┴──────┐                      ┌───────┴────────┐
    │  Modality   │                      │ Relay Listener │
    │  (SCU)      │                      │ (Populates DB) │
    └─────────────┘                      └────────────────┘
```

### Workflow

1. **Worklist Creation**: Relay listener receives appointments from web app and creates worklist items (NB not yet implemented; worklist items must be created programmatically via `scripts/add_worklist_item.py`)
2. **Worklist Query**: Modality sends C-FIND request to MWL server
3. **Filtering**: MWL server filters by modality, date, patient ID, status
4. **Response**: Server returns matching worklist items to modality
5. **Status Updates**: MPPS updates procedure status (NB not yet implemented)

## Running the MWL Server

The MWL server runs in a separate container:

```bash
# Start both PACS and MWL servers
docker compose up -d

# Start only MWL server
docker compose up -d mwl

# View logs
docker compose logs -f mwl

# Stop servers
docker compose down

# Reset databases
docker compose down -v
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MWL_AET` | `MWL_SCP` | Application Entity Title |
| `MWL_PORT` | `4243` | DICOM service port |
| `MWL_DB_PATH` | `/var/lib/pacs/worklist.db` | SQLite database path |
| `LOG_LEVEL` | `INFO` | Logging level |

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

# Send C-FIND
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

The PACS and MWL servers run in separate containers. See [ADR-003: Separate containers for PACS and MWL](../adr/ADR-003_Separate_containers_for_PACS_and_MWL.md) for the architectural decision and trade-offs.

**Docker Compose services:**
```yaml
services:
  pacs:
    container_name: pacs-server
    command: ["uv", "run", "python", "-m", "pacs_main"]
    ports:
      - "4244:4244"

  mwl:
    container_name: mwl-server
    command: ["uv", "run", "python", "-m", "mwl_main"]
    ports:
      - "4243:4243"
```

Each server:

- Runs in its own container
- Has its own Application Entity (AE)
- Uses a separate SQLite database
- Can be scaled and deployed independently
- Handles different DICOM operations (C-STORE vs C-FIND)
