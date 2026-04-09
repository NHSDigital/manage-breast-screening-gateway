# ADR-004: Daily backup and reset of the MWL database

Date: 2026-04-02

Status: Accepted

## Context

The gateway MWL database holds scheduled appointment data that is consumed by mammography modality via DICOM C-FIND. This data originates from Manage Breast Screening and is written to the gateway by the relay listener.

The worklist is inherently ephemeral: appointments are scheduled per clinic, and a clinic session does not span calendar days. Stale worklist items from a previous day are not meaningful to the modality and could cause confusion if they appeared in a C-FIND response.

The gateway MWL is not intended to be a canonical or long-term data store. Retaining worklist items indefinitely would cause the database to grow to unwieldy proportions and would give a false impression of data durability.

The gateway runs as a Python process on a Windows VM managed by Azure Arc. Scheduling therefore belongs in the infrastructure layer (Windows Task Scheduler, configurable via Arc).

## Decision

Reset the MWL database on a schedule managed by Windows Task Scheduler by:

1. Backing up the database before clearing it, using SQLite's native `conn.backup()` API
2. Deleting all rows from `worklist_items`

`reset_main.py` is performs these two steps and exits. Windows Task Scheduler (registered via `scripts/bat/schtasks.bat`) invokes it on whatever schedule is configured in infrastructure.

**Alternatives considered:**

- **In-process Python scheduler** (`croniter` sleep loop) — puts scheduling logic in application code; duplicates a facility the OS already provides; requires a long-running process that serves no other purpose
- **Reset on startup only** — would not handle long-running deployments where the process is not restarted between clinics
- **No reset** — leads to unbounded growth and stale data visible to the modality

## Consequences

### Positive Consequences

- Worklist is clean at the start of each clinic with no manual intervention
- Database size remains bounded
- Backup before clear means data is recoverable if needed
- Schedule is owned by infrastructure (Arc / Task Scheduler), not application code — no code change needed to adjust timing
- `reset_main.py` is a simple, testable, one-shot script with no scheduler machinery

### Negative Consequences

- Schedule configuration lives outside the codebase; requires infrastructure access to change
- Any worklist items written very close to the reset time could be cleared before the modality queries them. This is mitigated by choosing a reset time well outside clinic hours
- Backups accumulate on disk and will need periodic pruning; this is not currently automated
