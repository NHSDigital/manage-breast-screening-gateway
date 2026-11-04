# Live clinic debugging

> **When to use**: On-the-day support for a live clinic — checking worklist delivery,
> image receipt and upload from the gateway VM, and tracing problems through the
> Azure logs for both the gateway and Manage.

Two vantage points, in the order to try them:

- **Your laptop (Azure portal)** — Application Insights for both Manage and the
  gateway services, container app logs for Manage, and Azure Relay connection
  health. Needs only a read role (Monitoring Reader) on the prod resources.
  **Start here**: almost every question below is answerable from the portal.
- **The gateway VM** (RDP) — direct access to the MWL/PACS SQLite databases, DICOM
  storage and raw service logs. There is currently **no consistent remote route
  onto the Arc-deployed VMs**, so this relies on being granted RDP access when
  on-site. When available, this route allows us to inspect the databases and
  DICOM files.

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

## Symptom → first check

Portal checks first; the VM column is the escalation when telemetry isn't enough
(or isn't there).

| Symptom | From the portal | On the VM |
|---|---|---|
| Appointment checked in on Manage but not on the modality worklist | Manage App Insights: run the [relay trace trail](#worklist-sends-the-relay-trace-trail) — did the send confirm? If it failed, the error names the phase. If it confirmed: gateway App Insights, `cloud_RoleName == 'mwl-server'` traces while the modality refreshes | `Get-GwWorklist` — is the item in the DB? If no: `Watch-GwLog Relay`. If yes: `Watch-GwLog MWL` while the modality refreshes; confirm port 104 listening; scheduled_date is stored in **UTC** `YYYYMMDD` |
| Exposure taken but images not on the VM | Gateway App Insights: `cloud_RoleName == 'pacs-server'` traces while the modality sends | `Watch-GwLog PACS`; `Get-GwImages`; confirm port 11112 and that the modality is configured with AE title `RUBIE_PACS_PROD`, correct IP and port |
| Modality C-ECHO / worklist query times out | Nothing to see from Azure — this hop is modality → VM over the hospital LAN | Missing inbound Windows Firewall rules on the VM. Check the `firewall_rules` health check or `Get-NetFirewallRule -DisplayName "Rubie Gateway*"`; create the rules per the [onboarding runbook troubleshooting](./onboard-hospital-vm.md#modality-c-echo-dicom-ping-to-the-gateway-times-out) |
| Images on VM but not appearing in Manage | Gateway App Insights: `cloud_RoleName == 'upload-listener'` traces and exceptions. Auth errors usually mean the Arc managed identity / `Gateway.Access` app role or `Gateway.oid` in Manage is wrong. Cross-check Manage's side: `requests` on `/api/v1/dicom` | `Get-GwUploadFailures` — look at `upload_error` and `upload_attempt_count`; `Watch-GwLog Upload` |
| Item status stuck at SCHEDULED after procedure started | Gateway App Insights: `mwl-server` traces for MPPS N-CREATE/N-SET messages | `Get-GwWorklistItem <ACC>` — MPPS updates set `status` / `mpps_instance_uid`; check `Watch-GwLog MWL` |
| Anything crashing / restart loops | Gateway App Insights: `exceptions` table, any `cloud_RoleName` | `Search-GwLogs`; `Get-Service Gateway-*` (NSSM restarts failed services automatically — repeated banner lines in the log mean crash-looping) |

## From your laptop — Azure portal

Everything in this section is point-and-click plus pasted KQL. The resources live
in the **Breast Screening - Manage Breast Screening - Prod** subscription; open the
resource in the portal, go to **Logs**, paste the query. (Each query also runs
through `az monitor app-insights query` / `az monitor log-analytics query` if you
prefer a terminal — the KQL is identical.)

### Gateway service telemetry (Application Insights)

All four VM services send OpenTelemetry to **`ai-mbsgw-prod-arc-uks`**
(resource group `rg-mbsgw-prod-uks-arc-enabled-servers`). `cloud_RoleName` values:
`relay-listener`, `mwl-server`, `pacs-server`, `upload-listener`.

**Live Metrics** on that resource shows the services' output in real time —
useful to keep open during the clinic.

Errors and warnings in the last hour, all services:

```kql
traces
| where timestamp > ago(1h) and severityLevel >= 2
| project timestamp, cloud_RoleName, message
| order by timestamp desc
```

Exceptions with stack traces:

```kql
exceptions
| where timestamp > ago(4h)
| project timestamp, cloud_RoleName, type, outerMessage
| order by timestamp desc
```

Everything one service said in a window (e.g. the relay listener around a failure):

```kql
traces
| where timestamp > ago(1h) and cloud_RoleName == 'relay-listener'
| project timestamp, message
| order by timestamp desc
```

> Telemetry is a no-op if `APPLICATIONINSIGHTS_CONNECTION_STRING` wasn't set at
> deploy time — if queries return nothing at all, fall back to the VM logs and
> check the deploy log for the "Application Insights resource not found" warning.
> This is the one failure mode where the VM is the *only* source.

### Manage telemetry (Application Insights)

Manage's own telemetry is in **`appi-prod-uks-manbrs`** (resource group
`rg-manbrs-prod-uks`): every request, exception, log line and database call,
joined by `operation_Id`.

**Worklist sends — the relay trace trail**. A healthy send is three lines a few
seconds apart: `Acquired relay token …` → `Sent action …` → `Action … confirmed
by gateway via relay … in N.Ns`. A failure is logged with a `(phase: …)` marker
naming the hop that died (acquiring token / connecting / sending / waiting for
response / processing response):

```kql
traces
| where timestamp > ago(4h)
| where message startswith "Sent action"
    or message startswith "Acquired relay token"
    or message startswith "Action"
    or message startswith "Relay send failed"
| project timestamp, message, severityLevel, operation_Id
| order by timestamp asc
```

**Everything about one request**. Copy an `operation_Id` from any result, then:

```kql
union requests, traces, exceptions, dependencies
| where operation_Id == "<paste it here>"
| project timestamp, itemType, name, message, outerMessage, resultCode, duration
| order by timestamp asc
```

**Incoming DICOM uploads from the gateway** (the `/api/v1/dicom` endpoint):

```kql
requests
| where timestamp > ago(2h) and url contains "/api/v1/dicom"
| project timestamp, resultCode, duration, operation_Id
| order by timestamp desc
```

**Free-text search**: with a fragment and no query — an accession number, an
error phrase — use **Transaction search** on the resource and click through to
the end-to-end transaction view.

Manage-side data checks (worklist item actually created and sent?) are quickest in
the Django admin: **Gateway actions** — a healthy send is `status: confirmed`;
`failed` rows carry `last_error` and the retry schedule. The superuser gateway
test screen (`/gateway/tests/new/`) sends a live round-trip test against a
setting and shows status, failure hints and returned thumbnails as they happen —
for "is this site working right now", prefer it to raw KQL.

### Manage container logs (Log Analytics)

Raw container stdout and platform events live in the Log Analytics workspace
**`law-prod-uks-manbrs`** → **Logs** — the fallback when App Insights is silent
(startup crashes, ingestion gaps), and where the cron jobs' exits are recorded.

Worklist-send activity and errors from the gateway app code, as raw stdout:

```kql
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(2h)
| where Log_s has_any ('relay', 'GatewayAction', 'worklist', 'ERROR', 'Traceback')
| project TimeGenerated, Log_s
| order by TimeGenerated desc
```

Container and job lifecycle (did something die or restart?):

```kql
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(4h)
| where Reason_s == "ProcessExited" or Type_s == "Warning"
| project TimeGenerated, ContainerAppName_s, JobName_s, Reason_s, Log_s
| order by TimeGenerated desc
```

To live-stream a container's stdout instead, use the container app's **Log
stream** blade (or `az containerapp logs show -n <app-name> -g rg-manbrs-prod-uks
--type console --follow`).

### Azure Relay connection health

The namespace is `relay-manbrs-prod` in `rg-manbrs-prod-uks`; the hybrid
connection is `hc-<arc-machine-name>`.

In the portal: the namespace's **Hybrid Connections** blade lists each connection
with its **listener count** — `0` means `Gateway-Relay` on the VM is not
connected (check the service on the VM: `Watch-GwLog Relay`; look for "Connected -
waiting for worklist actions"). The namespace's **Metrics** blade plots
`ListenerConnections-Success`, `SenderConnections-Success` and
`ListenerConnections-ClientError` over the morning; sender client errors while
listeners are healthy point at the Manage side (its managed identity /
`AZURE_RELAY_CLIENT_ID`).

> **Beware the zombie listener**: a listener count of `1` does not prove the
> listener is *functional* — a connection that died without a clean close can
> stay registered while rendezvous dispatches go nowhere. The echo probe below is
> the truth test.

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
snippet in the script's docstring.

**Interpreting in-container DNS resolution**: prod Manage reaches the relay via a
**private endpoint**, so the relay hostname resolving to a **private IP** inside
the VNet is *correct*. During the July 2026 incident the PE silently blackholed
all traffic **while showing Approved** — likely an Azure-side fault or race at
PE creation; the interim fix was pointing DNS at the public endpoint, superseded
by deleting and recreating the PE. The health question is never "which IP family"
or "what does the PE state say" — it is **"does the echo come back"**.

Rotate the namespace key after a debugging session — nothing in a deployed
environment uses SAS, so rotation is free.

## On the gateway VM

Escalate here if you need to inspect database rows and DICOM files directly,
or a deploy that went out without telemetry. Getting on is the hard part —
interactive remote access to the Arc-deployed VMs is an unsolved problem, so in
practice this has meant arranging access through the trust. For non-interactive
inspection, Arc run commands are the established route (below) — everything in
this section works through them except the `Watch-GwLog` live tails.

The toolkit ships with the deployed release:

```powershell
. 'C:\Program Files\NHS\ManageBreastScreeningGateway\current\scripts\powershell\debug_toolkit.ps1'
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

### Remote inspection without RDP — Arc run commands

Arc run commands (`az connectedmachine run-command`) execute PowerShell on the
machine through Azure — no RDP session, no network path to the hospital. They
are already an established part of the workflow: the
[onboarding validation step](./onboard-hospital-vm.md#step-6--verify-acceptance-criteria)
and the [clinic preparation checks](./clinic-preparation.md) both use them. The
toolkit's `Get-Gw*` functions are non-interactive, so the database and
file-system checks above run the same way:

```bash
az connectedmachine run-command create \
  --machine-name <arc-machine-name> \
  --resource-group rg-mbsgw-prod-uks-arc-enabled-servers \
  --location uksouth \
  --name gw-debug-1 \
  --script ". 'C:\Program Files\NHS\ManageBreastScreeningGateway\current\scripts\powershell\debug_toolkit.ps1'; Get-GwHealth"
```

Output lands in `instanceView.output` in the result. Working rules:

- Use a **fresh `--name` per invocation**, and clean up afterwards: run commands
  execute **serially per machine** and accumulate as persistent resources — a
  stuck non-terminal one blocks every later deploy and diagnostic
  (`az connectedmachine run-command list -o table`; delete stragglers).
- The machine must show **Connected** (`az connectedmachine show … --query
  status`) — commands against an off/asleep VM queue indefinitely.
- Output is truncated — fine for toolkit summaries, not for dumping logs. Use
  `Search-GwLogs` or `Get-Content -Tail`, never `Watch-GwLog` (it follows and
  will never return).
- Keep it to metadata — worklist rows, upload failure counts, log excerpts.
  Don't pull DICOM or patient data through command output.
