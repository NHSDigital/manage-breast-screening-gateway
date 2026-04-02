# ADR-004: Daily backup and reset of the MWL database

Date: 2026-04-02

Status: Accepted

## Context

The gateway MWL database holds scheduled appointment data that is consumed by mammography modality via DICOM C-FIND. This data originates from Manage Breast Screening and is written to the gateway by the relay listener.

The worklist is inherently ephemeral: appointments are scheduled per clinic, and a clinic session does not span calendar days. Stale worklist items from a previous day are not meaningful to the modality and could cause confusion if they appeared in a C-FIND response.

The gateway MWL is not intended to be a canonical or long-term data store. Retaining worklist items indefinitely would cause the database to grow to unwieldy proportions and would give a false impression of data durability.

## Decision

Reset the MWL database on a configurable schedule (default: daily at 02:00 UTC) by:

1. Backing up the database before clearing it, using SQLite's native `conn.backup()` API
2. Deleting all rows from `worklist_items`

This runs as a dedicated `reset` container (`reset_main.py` / `MWLResetScheduler`).

The schedule is configured via a cron expression (`MWL_RESET_SCHEDULE`), which allows any cadence (daily, weekly, etc) to be expressed in a single environment variable without code changes.

**Alternatives considered:**

- **Reset on startup only** — would not handle long-running deployments where the container is not restarted between clinics
- **No reset** — leads to unbounded growth and stale data visible to the modality
- **Interval-based env vars** (`RESET_INTERVAL=daily`, `RESET_TIME=02:00`, `RESET_DAY=monday`) — more verbose config, requires code changes to support new intervals; cron expression is more expressive in a single value

## Consequences

### Positive Consequences

- Worklist is clean at the start of each clinic with no manual intervention
- Database size remains bounded
- Backup before clear means data is recoverable if needed
- Schedule is fully configurable via env var without code changes
- Follows the existing one-process-per-container pattern

### Negative Consequences

- Adds a fifth service to the deployment
- Any worklist items written very close to the reset time could be cleared before the modality queries them. This is mitigated by choosing a reset time well outside clinic hours
- Backups accumulate on disk and will need periodic pruning; this is not currently automated
