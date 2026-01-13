# ADR-003: Separate containers for PACS and MWL

Date: 2026-01-08

Status: Accepted

## Context

The Gateway needs to provide two DICOM services:

1. **PACS Server** - C-STORE operations for receiving medical images (port 4244)
2. **MWL Server** - C-FIND operations for modality worklist queries (port 4243)

These are distinct DICOM services with different protocols, different databases, and different responsibilities. However, they are both part of the same Gateway system and need to run together in production.

## Options Considered

### 1. Separate Containers
Each service runs in its own Docker container with dedicated entry points.

**Pros:**
- Independent scaling/deployment - Can scale/deploy PACS and MWL
- Operational flexibility - Can restart, debug or maintain services independently
- Better alignment with container best practices - One process per container

**Cons:**
- Slightly more resource overhead - Two separate container processes instead of one
- Additional configuration complexity - Need to manage two containers in orchestration

### 2. Separate Threads (Single Container)
Both services run in the same container using Python threading.

**Pros:**
- Operational simplicity - Single container to deploy, monitor and manage
- Shared resources - Both services share volume mounts and environment configuration
- Lower overhead - Threads have less overhead than separate processes

**Cons:**
- No independent scaling/deployment - Cannot scale/deploy PACS and MWL separately
- Shared failure domain - Issue with one service could affect the other

### 3. Separate Processes (Single Container)
Both services run in the same container using Python multiprocessing or a process manager.

**Pros:**
- True process isolation within a single container
- Can restart individual processes without container restart
- Better fault isolation than threads

**Cons:**
- More complex process management required
- Still cannot scale services independently
- More resource overhead than threads
- Need inter-processes communication mechanism if services need to communicate

### 4. Async Single Process
Both services run in the same async event loop.

**Pros:**
- Most efficient resource usage
- Single process to manage

**Cons:**
- More complex error handling - one service crash could bring down both
- Harder to debug
- Relatively more difficult to understand

## Decision

Run PACS and MWL servers in **separate Docker containers** using dedicated entry points.

**Key factors in this decision:**

1. **Independent scaling** - PACS may receive more load than MWL (or vice versa) during different times of day
2. **Independent deployment** - Ability to update one service without affecting the other
3. **Operational flexibility** - Ability to restart, debug or maintain one service independently
4. **Container best practices** - One process per container is the standard pattern
5. **Minimal trade-offs** - The resource overhead is minimal

## Consequences

### Positive Consequences

- **Independent scaling** - Can scale PACS and MWL based on their individual load patterns
- **Independent deployment** - Update one service without touching the other
- **Better observability** - Separate log streams and health checks for each service
- **Operational flexibility** - Can restart, debug or maintain services independently

### Negative Consequences

- **Slightly more resource usage** - Two separate processes instead of one (minimal overhead)
- **Multiple containers** - Requires separate containers and an orchestration strategy to manage both
