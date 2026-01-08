# ADR-003: Multi-threaded PACS and MWL server architecture

Date: 2026-01-08

Status: Accepted

## Context

The Gateway needs to provide two DICOM services:

1. **PACS Server** - C-STORE operations for receiving medical images (port 4244)
2. **MWL Server** - C-FIND operations for modality worklist queries (port 4243)

These are distinct DICOM services with different protocols, different databases, and different responsibilities. However, they are both part of the same Gateway system and need to run together in production.

Several deployment architectures were considered:

- **Separate containers** - Each service runs in its own container
- **Separate processes** - Both services in one container, using multiprocessing
- **Async single process** - Both services in one async event loop
- **Separate threads** - Both services in one container, using threading

## Decision

Run both PACS and MWL servers in the same container using separate Python threads.

**Implementation:**

```python
pacs_thread = threading.Thread(target=pacs_server.start, daemon=True)
mwl_thread = threading.Thread(target=mwl_server.start, daemon=True)

pacs_thread.start()  # Port 4244
mwl_thread.start()   # Port 4243

# Main thread keeps process alive
pacs_thread.join()
mwl_thread.join()
```

Each server:

- Runs independently with `block=True` on `AE.start_server()`
- Has its own Application Entity (AE)
- Uses a separate SQLite database

**Why this approach:**

- **Operational simplicity** - Single container to deploy, monitor, and manage
- **Shared resources** - Both services share the same volume mounts and environment configuration
- **pynetdicom compatibility** - The library's `AE.start_server()` is designed to block and handle connections, making threads a natural fit
- **Lower overhead** - Threads have less overhead than separate processes or containers

## Consequences

### Positive Consequences

- **Simple deployment** - One Docker Compose service, one container to manage
- **Shared configuration** - Environment variables, logging, and volumes managed in one place
- **Development workflow** - Single container to build, test, and debug locally

### Negative Consequences

- **No independent scaling or deployment** - Cannot scale or deploy PACS and MWL separately if one receives significantly more load
- **Restart granularity** - Cannot restart one service without restarting both

## Future Considerations

If load patterns show significant imbalance between PACS and MWL, or if independent scaling or modularisation becomes necessary, we could:

1. Split into separate containers while keeping the same codebase
2. Use a process manager run both processes in one container
