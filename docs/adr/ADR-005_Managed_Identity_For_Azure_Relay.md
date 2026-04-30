# ADR-005: Use Managed Identity for Azure Relay authentication

Date: 2026-04-28

Status: Accepted

## Context

The gateway connects to Azure Relay Hybrid Connections to receive worklist actions from Manage Breast Screening. A connection must be authenticated to Azure Relay.

The initial implementation used Shared Access Signature (SAS) tokens. These are HMAC-SHA256 signatures computed from a shared secret key, embedded in the WebSocket connection URL as a query parameter (`sb-hc-token`). This required:

- A shared access key to be provisioned and stored as an environment variable (`AZURE_RELAY_SHARED_ACCESS_KEY`)
- The key name to be configured separately (`AZURE_RELAY_KEY_NAME`)
- Manual key rotation when keys needed to change

As the gateway runs inside the hospital network but is provisioned via Azure Arc, it can be assigned a managed identity through Arc-enabled infrastructure. Storing a long-lived shared secret in the environment is therefore unnecessary operational overhead and a potential security risk.

That said, setting up a working Relay connection locally is already complex. Mandating managed identity for all environments would add further friction for developers, who would need Azure CLI credentials with a Relay Listener role assignment before they could run the service.

## Decision

In **production** (`ENVIRONMENT=prod`), the gateway uses `ManagedIdentityCredential` exclusively. The SAS token path is unavailable regardless of what environment variables are set. The gateway's managed identity must be assigned the **Azure Relay Listener** role on the hybrid connection resource in Azure.

In **non-production** environments, the auth method is determined by whether `AZURE_RELAY_SHARED_ACCESS_KEY` is set:

- If set, a SAS token is generated and embedded in the WebSocket URL (`sb-hc-token`), preserving the simpler local development setup.
- If absent, `DefaultAzureCredential` is used, which works with Azure CLI credentials (`az login`) for developers who have the Listener role assigned to their identity.

The token is passed as an `Authorization: Bearer` HTTP header on the WebSocket upgrade request for managed identity paths. Azure Relay validates it against Azure AD.

A startup credential check (`verify_credentials()`) runs before the listen loop. In production this will raise `ClientAuthenticationError` immediately if the managed identity is not correctly configured. In non-production with a SAS key it logs the auth method and continues.

`ManagedIdentityCredential` is preferred over `DefaultAzureCredential` in production because it is predictable — it only attempts the IMDS endpoint and fails clearly, rather than traversing a credential chain that could succeed unexpectedly via another mechanism.

## Consequences

### Positive Consequences

- **No secrets in production:** No shared key to store, rotate, or accidentally leak in deployed environments
- **Fail-fast on misconfiguration:** Startup validation raises `ClientAuthenticationError` immediately rather than failing silently in the reconnect loop
- **Preserved local developer experience:** SAS tokens continue to work locally when `AZURE_RELAY_SHARED_ACCESS_KEY` is set
- **Consistent with platform direction:** Aligns with how the gateway already authenticates to the DICOM API

### Negative Consequences

- **Azure infrastructure dependency in production:** The managed identity and its role assignment must exist before the service can start
