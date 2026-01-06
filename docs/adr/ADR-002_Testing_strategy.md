# ADR-002: Testing strategy

Date: 2025-12-31

Status: Accepted

## Context

Manage Breast Screening Gateway runs as a daemon or 'server' within an NHS Trust network.

In order to ensure the Gateway can process DICOM events correctly, automated tests in this repository are run in the Continuous Integration pipeline (CI).

These ensure data is processed correctly by emulating DICOM events, they also guard against breaking code changes and regression.

It is impractical to test the entire distributed Manage Breast Screening + PACS ecosystem.
Some form of emulation is necessary to allow the volume of specific testing needed to ensure detailed code coverage.
The test suite running in our CI pipeline needs to provide sufficient code coverage and be performant enough to run frequently.

## Decision

Unit tests use mocked dependencies to keep the test setup to a minimum.
Integration tests use real dependencies like the SQLite3 database and the filesystem for storage.
Integration tests also run the Gateway server in a separate Python Thread in order to test the externals of the overall system.

## Consequences

The test suite is modular and fast.
Unit tests can be run in isolation with `make test-unit`.
Integration tests can also be run in isolation with `make test-integration`
The entire suite can be run with `make test`

### Positive Consequences

- Quicker development workflow given the ability to focus on specific tests
- Separation of testing strategies allows unit tests to permeate all logic flow, while integration tests cover a broader scope.
- Overlap of test coverage between unit and integration tests provides more resilience when making code changes.
- CI performance is not impacted by comprehensive code coverage.

### Negative Consequences

- Testing overlap can mean more laborious code changes.
- Running Gateway process in Thread adds complexity, albeit less general overhead than running multiple containers.
