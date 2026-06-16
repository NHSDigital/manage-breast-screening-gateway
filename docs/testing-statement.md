# Rubie Gateway — Testing Statement

**Purpose:** Describe how the Rubie Gateway is tested, what is and is not covered by automated testing, and where test evidence can be found.
**Status:** Living document — figures reflect the state of `main` and should be refreshed when materially changed.

---

## 1. What the gateway does (context for scope)

The Rubie Gateway is a Python application that runs on a VM inside an NHS Trust network and bridges the on-site imaging modality and the cloud-based Rubie service. Its responsibilities are:

- **MWL (Modality Worklist) SCP** — receives worklist create/update commands from Rubie (via Azure Relay), and serves them to the modality over DICOM C-FIND.
- **PACS SCP** — receives acquired images from the modality over DICOM C-STORE, and answers DICOM C-ECHO connectivity checks.
- **Upload service** — forwards stored images to the Rubie cloud API.
- **Relay listener** — maintains the Azure Relay connection over which Rubie sends commands.

Testing is scoped to the behaviour of this application. The wider distributed system (Rubie cloud, NBSS, the Trust PACS, the physical modality) is out of scope for automated testing here.

## 2. Testing approach

The strategy is recorded in [ADR-002: Testing strategy](./adr/ADR-002_Testing_strategy.md). In summary, the suite is layered:

| Layer | What it exercises | Dependencies |
| --- | --- | --- |
| **Unit** | Individual functions and classes in isolation | Mocked |
| **Integration** | Components working together, including the gateway server running in a background thread | Real SQLite database, real filesystem |
| **End-to-end (in-process)** | A full relay-command → MWL → C-STORE → upload flow | Real SQLite + filesystem; external network boundaries emulated |

Because it is impractical to stand up the entire Rubie + PACS + modality ecosystem for automated testing, the suite uses **emulation** at the system boundaries: crafted DICOM datasets and a modality emulator stand in for real imaging hardware, and the Azure Relay transport is mocked so command-processing logic can be tested deterministically.

## 3. What is covered

Automated tests cover the core DICOM and messaging behaviour, including:

- **MWL**: C-FIND worklist queries (including patient-name search), worklist item creation, and status transitions.
- **PACS**: C-STORE image receipt and metadata persistence, handling of already-stored SOP instances, and C-ECHO verification (both PACS and MWL application entities).
- **Relay listener**: processing of inbound action commands and dispatch to the correct handler.
- **Upload**: forwarding of stored instances to the Rubie API.
- **Modality emulator**: worklist querying and image generation used to drive end-to-end tests.

**Current figures (refresh on material change):**

- **Over 200 automated tests** (194 unit, 19 integration), all passing on `main`.
- **Approximately 90% line coverage** of application code (`src/`), measured by `pytest-cov` and reported to Codecov on every run.

## 4. Automated quality gates (CI)

Every pull request and every merge to `main` runs the following in GitHub Actions; all must pass before code is deployable:

| Stage | Check | Tool |
| --- | --- | --- |
| Commit | Secret scanning across branch history | gitleaks |
| Test | Full unit + integration suite | pytest |
| Test | Line-coverage measurement and reporting | pytest-cov / Codecov |
| Test | Linting and formatting | ruff |
| Test | Static type checking | pyright |
| Scheduled | Static application security testing (SAST) | CodeQL (weekly) |

## 5. Test evidence

- **Per-run evidence:** the GitHub Actions run for each PR and each `main` build records the full test output, pass/fail status, and coverage upload. These are retained against the commit and pull request.
- **Coverage trend:** reported to Codecov, giving per-file coverage and change-over-time.
- **Local reproduction:** the full suite is `make test`; subsets are `make test-unit` and `make test-integration`. Coverage HTML is written to `htmlcov/`.
- **Published report:** a human-readable test report is published to GitHub Pages on every `main` build and is available at <https://nhsdigital.github.io/manage-breast-screening-gateway/>. This gives assurance reviewers a stable link to the latest results without navigating CI logs, and is refreshed automatically per build.

## 6. What is NOT covered by automated testing

| Not automatically tested | Why | Compensating assurance |
| --- | --- | --- |
| **Real modality hardware** | No physical modality in CI | Emulated with crafted DICOM and the modality emulator; validated against real Hologic kit during site dry runs. |
| **Live Azure Relay / Managed Identity auth** | No Azure resources in CI; the transport is mocked | Credential and connection logic is exercised by deployments to dev/pre-prod and by post-deployment smoke tests. |
| **PowerShell deployment scripts** (`deploy.ps1`, `rollback.ps1`) | Windows blue/green cutover, NSSM service install and rollback are not unit-testable in this suite | Exercised by real deployments to non-production environments with smoke tests; Bash helper scripts are covered by ShellCheck. |
| **The end-to-end distributed system** (Rubie cloud, NBSS, Trust PACS) | Impractical to assemble for automated testing (ADR-002) | Emulation at boundaries; manual/clinical validation via site dry runs. |

## 7. Maintaining this statement

This statement should be reviewed when the testing strategy changes materially — for example a new test layer, a significant coverage change, a new CI gate, or a change to what is emulated versus tested against real dependencies. The figures in §3 are point-in-time and can be regenerated with `make test`.
