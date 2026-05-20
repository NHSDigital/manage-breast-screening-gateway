# ADR-006: Use a modality emulator for non-production environments

Date: 2026-06-15

Status: Accepted

## Context

The Manage Breast Screening service sends worklist items corresponding to screening appointments as the appointment starts. These are received by the gateway via Azure Relay and processed to trigger DICOM API uploads of the screening study data. The worklist items are queried via DICOM C-FIND requests to the gateway MWL server and stored on the gateway PACS server using the DICOM C-STORE protocol.

In production this query is performed by the modality, which is a physical machine in the hospital network that runs software to query the MWL and display results to radiographers. The modality then sends the resulting study DICOM files to the Gateway PACS server using C-STORE. The PACS server then compresses the image data in the DICOM files and uploads it to the DICOM API hosted on Manage.

In non-production environments, there is no modality available to perform this query. This means that testing the full flow of worklist items through the gateway and into the DICOM API is difficult without deploying to production or using complex stubs/mocks.

## Decision

To facilitate end-to-end testing of the worklist flow in non-production environments, we will implement a simple modality emulator. This will be a lightweight service that simulates the behavior of a real modality by performing queries against the MWL server and storing the emulated study data on the Gateway PACS server, mimicking the behavior of a real modality.

The emulator runs on the same host as the MWL and PACS servers in non-production environments. It runs as a Python process that makes a C-FIND request at a configurable polling interval, checking for new worklist items. When it finds a new item, it creates a DICOM dataset from the worklist details, includes some sample image data and sends them to the PACS server via C-STORE.

The sample image data corresponds to the 4 main laterality and view position combinations (LCC, LMLO, RCC, RMLO) to allow testing of the laterality and view position logic in the gateway images screens as the DICOM files are uploaded to Manage.

## Consequences

We no longer have to use a third party emulator or do any UI work to test the happy path of worklist items flowing through the gateway and into the DICOM API in non-production environments. This also allows us to make more comprehensive end-to-end tests that cover the full flow, including the C-FIND and C-STORE interactions with the MWL and PACS servers.

### Positive Consequences

- **End-to-end testing:** Enables testing of the full worklist flow in non-production environments without needing a physical modality or complex stubs/mocks.
- **Simplified test setup:** Developers can run the emulator locally or in test environments to simulate modality behavior without additional infrastructure.
- **Improved test coverage:** Allows for more comprehensive tests that cover the interactions with the MWL and PACS servers, as well as the gateway's processing logic for worklist items.
- **Configurable behavior:** The emulator can be configured to simulate different scenarios, such as varying polling intervals or different worklist item details, to test edge cases and error handling in the gateway.

### Negative Consequences

- The emulator and sample images are packaged with every release. This increases the size of the release artifact and may have implications for storage and distribution.
