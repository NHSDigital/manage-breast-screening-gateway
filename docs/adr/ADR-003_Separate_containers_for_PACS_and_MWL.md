# ADR-003: Separate containers for PACS and MWL

Date: 2026-01-08

Status: Accepted

## Context

The Gateway needs to provide DICOM services that must run together in production:

1. **PACS Server** - C-STORE operations for receiving medical images (port 4244)
2. **MWL Server** - C-FIND operations for modality worklist queries (port 4243)

Several deployment architectures were considered, including running both servers in separate threads within a single container. However, the team identified requirements that made separate containers a better fit:

1. **Independent scaling** - PACS may receive more load than MWL (or vice versa) and needs to scale independently
2. **Independent deployment** - Ability to update one service without restarting the other
3. **Operational flexibility** - Ability to restart, debug, or maintain one service independently
4. **Better alignment with container best practices** - One process per container is the standard pattern
5. **Clearer resource management** - Separate containers make it easier to monitor and allocate resources

## Decision

Run PACS and MWL servers in separate Docker containers using dedicated entry points.

**Implementation:**

Created two entry point modules:
- `pacs_main.py` - Starts only the PACS server
- `mwl_main.py` - Starts only the MWL server

## Consequences

### Positive Consequences

- **Independent scaling** - Can scale PACS and MWL based on their individual load patterns
- **Independent deployment** - Update one service without touching the other
- **Better observability** - Separate log streams and health checks for each service
- **Operational flexibility** - Can restart, debug, or maintain services independently

### Negative Consequences

- **Slightly more resource usage** - Two separate processes instead of one (minimal overhead)
