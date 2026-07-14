# Live clinic debugging

> **When to use**: On-the-day support for a live clinic — checking worklist delivery,
> image receipt and upload from the gateway VM, and tracing problems through the
> Azure logs for both the gateway and Manage.

Two vantage points:

- **The gateway VM** (RDP) — direct access to the MWL/PACS SQLite databases, DICOM
  storage and service logs. Use [`scripts/powershell/debug_toolkit.ps1`](../../../scripts/powershell/debug_toolkit.ps1).
- **Your laptop** (Azure CLI / portal) — Application Insights for the gateway
  services, container app logs for Manage, and Azure Relay connection health.

## The pipeline at a glance

```
Manage (container app)
   │  worklist item ─── Azure Relay (relay-manbrs-prod / hc-<machine>) ──► Gateway-Relay
   │                                                                          │
   │                                                              writes data\worklist.db
   │                                                                          │
Modality ── C-FIND (port 104) ──► Gateway-MWL ◄── reads worklist.db ──────────┘
Modality ── C-STORE (port 11112) ──► Gateway-PACS ──► data\storage + data\pacs.db
                                                              │
Manage /api/v1/dicom ◄── HTTPS upload (managed identity) ── Gateway-Upload
```

A failure at any hop has a distinct signature — the sections below work through them
in pipeline order.

## On the gateway VM

Copy `debug_toolkit.ps1` to the VM (or paste it into an editor there), then:

```powershell
. .\debug_toolkit.ps1
Get-GwHealth        # start here: services, ports, relay connection, disk
```

Reference points:

| Thing | Where |
|---|---|
| Install root | `C:\Program Files\NHS\ManageBreastScreeningGateway` |
| Services (NSSM) | `Gateway-Relay`, `Gateway-MWL`, `Gateway-PACS`, `Gateway-Upload` |
| Worklist DB (SQLite) | `data\worklist.db` — table `worklist_items` |
| PACS DB (SQLite) | `data\pacs.db` — table `stored_instances` |
| DICOM files | `data\storage\` (hash-based directory layout; use `Get-GwDicomFiles`) |
| Service logs | `logs\Gateway-<Service>.log` (NSSM stdout+stderr) |
| Deployment logs | `logs\deployments\deploy-*` |
| Config | `.env` in the install root |
| MWL | AET `RUBIE_MWL_PROD`, port 104 |
| PACS | AET `RUBIE_PACS_PROD`, port 11112 |

### Symptom → first command

| Symptom | Check |
|---|---|
| Appointment checked in on Manage but not on the modality worklist | `Get-GwWorklist` — is the item in the DB? If **no**: relay hop failed → `Watch-GwLog Relay`, then the Azure Relay + Manage sections below. If **yes**: modality⇄MWL hop → `Watch-GwLog MWL` while the modality refreshes; confirm port 104 listening; scheduled_date is stored in **UTC** `YYYYMMDD` |
| Exposure taken but images not on the VM | `Watch-GwLog PACS` while the modality sends; `Get-GwImages`; confirm port 11112 and that the modality is configured with AE title `RUBIE_PACS_PROD`, correct IP and port |
| Images on VM but not appearing in Manage | `Get-GwUploadFailures` — look at `upload_error` and `upload_attempt_count`; `Watch-GwLog Upload`. Auth errors here usually mean the Arc managed identity / `Gateway.Access` app role or `Gateway.oid` in Manage is wrong |
| Item status stuck at SCHEDULED after procedure started | `Get-GwWorklistItem <ACC>` — MPPS updates set `status` / `mpps_instance_uid`; check `Watch-GwLog MWL` for MPPS N-CREATE/N-SET messages |
| Anything crashing / restart loops | `Search-GwLogs`; `Get-Service Gateway-*` (NSSM restarts failed services automatically — repeated banner lines in the log mean crash-looping) |

## From your laptop — Azure

```bash
az account set --subscription "Breast Screening - Manage Breast Screening - Prod"
```

### Gateway service telemetry (Application Insights)

All four VM services send OpenTelemetry to `ai-mbsgw-prod-arc-uks`
(resource group `rg-mbsgw-prod-uks-arc-enabled-servers`). `cloud_RoleName` values:
`relay-listener`, `mwl-server`, `pacs-server`, `upload-listener`.

```bash
# Errors and warnings in the last hour, all services
az monitor app-insights query \
  --app ai-mbsgw-prod-arc-uks -g rg-mbsgw-prod-uks-arc-enabled-servers \
  --analytics-query "traces
    | where timestamp > ago(1h) and severityLevel >= 2
    | project timestamp, cloud_RoleName, message
    | order by timestamp desc" -o table

# Exceptions with stack traces
az monitor app-insights query \
  --app ai-mbsgw-prod-arc-uks -g rg-mbsgw-prod-uks-arc-enabled-servers \
  --analytics-query "exceptions
    | where timestamp > ago(4h)
    | project timestamp, cloud_RoleName, type, outerMessage
    | order by timestamp desc" -o table

# Everything one service said in a window (e.g. relay listener around a failure)
az monitor app-insights query \
  --app ai-mbsgw-prod-arc-uks -g rg-mbsgw-prod-uks-arc-enabled-servers \
  --analytics-query "traces
    | where timestamp > ago(1h) and cloud_RoleName == 'relay-listener'
    | project timestamp, message | order by timestamp desc" -o table
```

Portal equivalent: the App Insights resource → **Logs**, or **Live Metrics** for
real-time output during the clinic.

> Telemetry is a no-op if `APPLICATIONINSIGHTS_CONNECTION_STRING` wasn't set at
> deploy time — if queries return nothing at all, fall back to the VM logs and
> check the deploy log for the "Application Insights resource not found" warning.

### Azure Relay connection health

The namespace is `relay-manbrs-prod` in `rg-manbrs-prod-uks`; the Hull hybrid
connection is `hc-<arc-machine-name>`.

```bash
# Does the HC exist / listener count (listenerCount > 0 means the VM is connected)
az relay hyco show --namespace-name relay-manbrs-prod -g rg-manbrs-prod-uks \
  -n hc-gw-hull-university-teaching-hospitals-nhs-trust-rwa-01 \
  --query "{name:name, listenerCount:listenerCount}"

# Namespace metrics: listeners and sender connections over the morning
az monitor metrics list \
  --resource "$(az relay namespace show -g rg-manbrs-prod-uks -n relay-manbrs-prod --query id -o tsv)" \
  --metric "ListenerConnections-Success" "SenderConnections-Success" "ListenerConnections-ClientError" \
  --interval PT5M --offset 4h -o table
```

`listenerCount: 0` means `Gateway-Relay` on the VM is not connected — check the
service on the VM (`Watch-GwLog Relay`; look for "Connected - waiting for worklist
actions"). Sender client errors while listeners are healthy point at the Manage side
(its managed identity / `AZURE_RELAY_CLIENT_ID`).

> **Beware the zombie listener**: `listenerCount: 1` does not prove the listener is
> *functional* — a connection that died without a clean close can stay registered
> while rendezvous dispatches go nowhere. The echo probe below is the truth test.

### The echo probe — test the relay → gateway path without Manage

[`scripts/diagnostics/relay_echo_probe.py`](../../../scripts/diagnostics/relay_echo_probe.py)
connects to the hybrid connection **as a sender** (exactly like Manage does), sends an
`echo` action — which the relay listener answers without touching its database — and
waits for the reply. It needs only Python, `pip install websockets`, and a credential;
no Azure login, runnable from any laptop.

```bash
python scripts/diagnostics/relay_echo_probe.py \
  --namespace relay-manbrs-prod.servicebus.windows.net \
  --hc hc-gw-hull-university-teaching-hospitals-nhs-trust-rwa-01 \
  --key '<RootManageSharedAccessKey value>'   # namespace-level key, NOT the HC's listen-only key
```

| Result | Meaning |
|---|---|
| `RESPONSE` in <1s | Relay and gateway listener fully healthy → the fault is on Manage's side |
| `TIMEOUT` waiting for reply | Sender accepted but listener never answered → zombie listener or gateway-side fault; restart `Gateway-Relay` and retry |
| `CONNECT FAILED: HTTP 401` | Bad key — the per-HC `listen` policy key cannot send; use the namespace root key |
| `CONNECT FAILED: HTTP 404` | Wrong HC name, or no listener registered at all |

There is also `--bearer-token` mode (see the script's docstring) to test the AAD
bearer path Manage uses in production. To run the probe from *inside* the Manage
container (testing Manage's actual network/DNS/identity), see the container-side
snippet in the script's docstring — during the July 2026 incident that variant is
what exposed the relay hostname resolving to a private endpoint IP inside the VNet.

Rotate the namespace key after a debugging session — nothing in a deployed
environment uses SAS, so rotation is free.

### Manage application logs

Discover the names once (they come from the shared naming module, so don't guess):

```bash
az containerapp list -g rg-manbrs-prod-uks --query "[].name" -o tsv
az monitor log-analytics workspace list -g rg-manbrs-prod-uks --query "[].{name:name, id:customerId}" -o table
```

Then either live-stream:

```bash
az containerapp logs show -n <app-name> -g rg-manbrs-prod-uks --type console --follow --tail 50
```

or query Log Analytics (better for searching):

```bash
# Worklist-send activity and errors from the gateway app code
az monitor log-analytics query --workspace <workspace-customer-id> \
  --analytics-query "ContainerAppConsoleLogs_CL
    | where TimeGenerated > ago(2h)
    | where Log_s has_any ('relay', 'GatewayAction', 'worklist', 'ERROR', 'Traceback')
    | project TimeGenerated, Log_s | order by TimeGenerated desc" -o table

# Incoming DICOM uploads from the gateway (the /api/v1/dicom endpoint)
az monitor log-analytics query --workspace <workspace-customer-id> \
  --analytics-query "ContainerAppConsoleLogs_CL
    | where TimeGenerated > ago(2h)
    | where Log_s has 'dicom'
    | project TimeGenerated, Log_s | order by TimeGenerated desc" -o table
```

Manage-side data checks (worklist item actually created and sent?) are quickest in
the Django admin: **Gateway actions** — a healthy send is `status: confirmed`;
`failed` rows carry `last_error` and the retry schedule.

## Pre-flight checklist (run before the clinic starts)

On the VM:

1. `Get-GwHealth` — all four services **Running**, ports 104 and 11112 listening,
   relay log shows "Connected - waiting for worklist actions", disk has headroom.
2. `Get-GwWorklist` — after the first participant is checked in on Manage, the item
   appears here within seconds. That one check proves Manage → Relay → VM end to end.
3. On the modality: query the worklist and confirm the participant is listed.

From the laptop:

4. `az relay hyco show ... --query listenerCount` returns ≥ 1.
5. App Insights errors query over `ago(12h)` is quiet (no crash loops overnight).

## During the clinic — a useful passive setup

On the VM, keep two windows open:

```powershell
Watch-GwLog PACS     # window 1 — see each C-STORE arrive
Watch-GwLog Upload   # window 2 — see each upload to Manage
```

After each participant: `Get-GwImages` should show the expected image count with
`uploaded` equal to `images` within a minute or two.
