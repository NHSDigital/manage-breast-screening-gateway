# Hospital VM Onboarding Runbook

> **Script**: `scripts/powershell/arc-setup.ps1`
> **When to use**: Onboarding a new NHS hospital gateway VM to Azure Arc for the first time

---

## Prerequisites

- [ ] Hospital IT has provisioned the gateway VM (Windows Server 2022 or later)
- [ ] VM has outbound internet access to:
  - `*.arc.azure.com`
  - `*.his.arc.azure.com`
  - `relay-manbrs-<env>.servicebus.windows.net`
- [ ] Trust ODS code confirmed via the [ODS portal](https://odsportal.nhsbsa.nhs.uk/)
- [ ] NHS region confirmed (`nw` | `neyh` | `mids` | `eoe` | `lon` | `se` | `sw`)
- [ ] Deployment ring agreed with the programme team
- [ ] Onboarding engineer has the permissions listed below
- [ ] Temporary onboarding secret created (Step 0) ready to share on the onboarding call

## Who can run this

The engineer driving the onboarding needs, for the target environment:

| Requirement | Why |
| --- | --- |
| Membership of `screening_mbsgw_<env>` (PIM-activated) | Access to the gateway spoke subscription |
| PIM roles activated for **both** the Core Services hub and the Manage Breast Screening spoke subscriptions | Deployment tooling runs against the hub subscription and writes to the spoke, so both are needed during onboarding |
| **Owner** of the `spn-manbrs-web-api-<env>` enterprise application *and* its app registration | Required to run `assign-arc-app-roles` (Step 3) |
| Rights to create client secrets on the `spn-azure-arc-onboarding-screening-<env>` app registration | Step 0 |

> The pipeline's managed identity additionally requires the **Monitoring Contributor** role. This is assigned by the environment's infrastructure code, not by hand — if it is missing, fix it in code rather than in the portal.

---

## Step 0 — Create a temporary onboarding secret

In the Azure portal: **App registrations → `spn-azure-arc-onboarding-screening-<env>` → Certificates & secrets → New client secret**, with:

- **Description**: identify the hospital (e.g. `Somerset-NHS-Foundation-Trust - Arc onboarding`)
- **Expiry**: custom, **24 hours** from creation

Then:

- Copy the **secret value** immediately — it is shown only once.
- Record the **Secret ID** for audit and revocation.
- Store the value securely. Provide it to the hospital IT engineer **only during the onboarding call** — never in advance, never over unsecured channels.

---

## Step 1 — Determine site parameters

The Arc resource name is built automatically from `SiteName`, `ODSCode`, and `Instance`:

```text
gw-<SiteName>-<ODSCode>-<Instance>
```

All lowercase, hyphens only. Azure constraint: max 54 characters (`a-z A-Z 0-9 - _ .`).

| Parameter | Format | Example |
|-----------|--------|---------|
| `SiteName` | Trust name, hyphen-separated, no spaces | `Hull-University-Teaching-Hospitals-NHS-Trust` |
| `ODSCode` | ODS code (uppercase input, lowercased in name) | `RWA` |
| `Instance` | Zero-padded instance number | `01` |
| `NHSRegion` | One of: `nw` `neyh` `mids` `eoe` `lon` `se` `sw` | `neyh` |
| `SiteType` | `static` or `mobile` | `static` |
| `DeploymentRing` | `ring1`–`ring4` (see below) | `ring1` |

> **Example**: `SiteName=Hull-University-Teaching-Hospitals-NHS-Trust`, `ODSCode=RWA`, `Instance=01`
> → Arc resource name: `gw-hull-university-teaching-hospitals-nhs-trust-rwa-01` (54 chars — at the limit)

**Ring assignments:**

| Ring | Sites |
|------|-------|
| ring0 | Test VM only (`mbsgw-review`) |
| ring1 | 1 site per PACS vendor (first real sites) |
| ring2 | 1 site per NHS region |
| ring3 | Remaining static sites |
| ring4 | Mobile units |

## Step 2 — Run Arc onboarding script on the gateway VM

Copy [`scripts/powershell/arc-setup.ps1`](../../../scripts/powershell/arc-setup.ps1) to the VM and run from an **elevated PowerShell session**.

If script execution is disabled on the VM, allow it for the current session first:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

> This only affects the current PowerShell process and does not change the machine-wide policy.
> If the script was downloaded from the internet and is still blocked, see [Script execution blocked](#script-execution-blocked) in Troubleshooting.

```powershell
.\arc-setup.ps1 `
    -SubscriptionId         "<spoke-subscription-id>" `
    -TenantId               "<tenant-id>" `
    -ResourceGroup          "rg-mbsgw-<env>-uks-arc-enabled-servers" `
    -Location               "uksouth" `
    -ServicePrincipalId     "<arc-onboarding-spn-client-id>" `
    -ServicePrincipalSecret "<arc-onboarding-spn-client-secret>" `
    -SiteName               "Hull-University-Teaching-Hospitals-NHS-Trust" `
    -ODSCode                "RWA" `
    -Instance               "01" `
    -NHSRegion              "neyh" `
    -SiteType               "static" `
    -DeploymentRing         "ring1"
```

The script will:

1. Install the Azure Arc agent (`azcmagent`) if not already present
2. Build the Arc resource name: `gw-hull-university-teaching-hospitals-nhs-trust-rwa-01`
3. Stamp site metadata as tags on the Arc machine resource
4. Connect the VM to Azure Arc with `--resource-name` set to the built resource name

Logs are written to `C:\ArcSetup\ArcSetup.log`.

**Verify**: In the Azure portal, navigate to `rg-mbsgw-<env>-uks-arc-enabled-servers` → Azure Arc machines → `gw-hull-university-teaching-hospitals-nhs-trust-rwa-01`. Status should be **Connected**.

## Step 3 — Grant API access

> [!IMPORTANT]
> Without this step the gateway services will start but fail to authenticate against the cloud web API. The Arc machine's managed identity must be assigned the `Gateway.Access` app role on `spn-manbrs-web-api-<env>` before the first deployment.

Run from a developer machine with Owner access to the enterprise application:

```bash
make <env> assign-arc-app-roles
```

This calls [`scripts/bash/assign_arc_app_roles.sh`](../../../scripts/bash/assign_arc_app_roles.sh) which discovers all Arc machines in `rg-mbsgw-<env>-uks-arc-enabled-servers` and assigns the `Gateway.Access` role to each machine's managed identity.

> **Why is this manual?** The pipeline managed identity (`mi-mbsgw-<env>-adotoaz-uks`) cannot create app role assignments via the pipeline — Microsoft Graph requires `AppRoleAssignment.ReadWrite.All` in application auth context regardless of SP ownership, and this permission cannot be granted under the organisation's Entra policy. Running `assign-arc-app-roles` under a user account with ownership of the enterprise app SP is sufficient. See [Deployment Pipeline — Section 12](../deployment-pipeline.md#12-pipeline-identities-and-permissions) for details.

**Verify**: In the Azure portal navigate to **Enterprise Applications → spn-manbrs-web-api-\<env\> → Users and groups**. The Arc machine (`gw-hull-university-teaching-hospitals-nhs-trust-rwa-01`) should appear with the `Gateway.Access` role.

## Step 4 — Trigger Terraform to provision the Hybrid Connection

Run the **`manage-breast-screening-gateway`** GitHub Actions workflow manually, selecting the appropriate environment (`dev`, `preprod`, or `prod`).

This workflow will trigger the **Deploy to Azure - \`<env\>`** and **Deploy Gateway App - `<env>`** Azure DevOps pipelines in the **manage-breast-screening-gateway** Azure DevOps project: https://dev.azure.com/nhse-dtos/manage-breast-screening-gateway.

Terraform discovers the new Arc machine and creates:

- `hc-gw-hull-university-teaching-hospitals-nhs-trust-rwa-01` in the relay namespace (`relay-manbrs-<env>`)
- `listen` auth rule on that Hybrid Connection

**Verify**: In the Azure portal, navigate to `relay-manbrs-<env>` → Hybrid Connections → `hc-gw-hull-university-teaching-hospitals-nhs-trust-rwa-01` is present.

> **If the relay namespace itself is missing** (new environment): it is provisioned by the **dtos-manage-breast-screening** repo (`enable_relay = true` in that environment's tfvars), into the Manage spoke subscription — **not** the hub. See [Create Environment](../infrastructure/create-environment.md).

## Step 5 — Deploy the gateway application

Run the ADO pipeline **Deploy Gateway - \<env\>** with:

```text
targetSiteCode : gw-hull-university-teaching-hospitals-nhs-trust-rwa-01
releaseTag     : latest        (or a specific tag, e.g. v1.2.3)
```

The pipeline:

1. Retrieves the listen SAS key for `hc-gw-hull-university-teaching-hospitals-nhs-trust-rwa-01`
2. Sends an Arc Run Command to `gw-hull-university-teaching-hospitals-nhs-trust-rwa-01` that writes `.env` and runs `deploy.ps1`
3. Polls for completion and reports success or failure

## Step 6 — Verify (acceptance criteria)

Onboarding is complete when **all** of the following hold:

- [ ] The deployment pipeline completed with no errors or failed stages
- [ ] The Arc machine shows **Connected** in the portal
- [ ] The Hybrid Connection `hc-gw-<site>-<ods>-<instance>` shows **1 listener**
- [ ] The validation command below succeeds (`executionState: Succeeded`, `exitCode: 0`) showing all four services **Running** and ports **104** and **11112** listening
- [ ] The relay listener log ends with `Connected - waiting for worklist actions...`
- [ ] No manual intervention was needed after the pipeline completed

Validation command (or run the script block directly on the VM):

```bash
az connectedmachine run-command create \
  --machine-name gw-<site>-<ods>-<instance> \
  --resource-group rg-mbsgw-<env>-uks-arc-enabled-servers \
  --location uksouth \
  --name check-services-1 \
  --script "Get-Service Gateway-PACS, Gateway-MWL, Gateway-Upload, Gateway-Relay | Format-Table Name, Status; Get-NetTCPConnection -State Listen | Where-Object { \$_.LocalPort -in 104, 11112 } | Format-Table LocalAddress, LocalPort"
```

Expected output (in `instanceView.output`):

```text
Name           Status
----           ------
Gateway-MWL    Running
Gateway-PACS   Running
Gateway-Relay  Running
Gateway-Upload Running

LocalAddress LocalPort
------------ ---------
0.0.0.0          11112
0.0.0.0            104
```

Relay listener check (same pattern, fresh `--name`):

```bash
  --script "Get-Content 'C:\Program Files\NHS\ManageBreastScreeningGateway\logs\Gateway-Relay.log' | Where-Object { \$_ -notmatch 'opentelemetry' } | Select-Object -Last 5"
```

Expected: the last line is `Connected - waiting for worklist actions...`

> A **Running** service that has not logged `Connected - waiting` is not healthy — the relay connection is the part that matters. Do not rely on the Log Analytics heartbeat as a liveness signal: telemetry export from gateway VMs is a known issue at the time of writing.

---

## Parameters reference

| Parameter | Required | Default | Description |
| --------- | -------- | ------- | ----------- |
| `-SubscriptionId` | Yes | — | Azure spoke subscription ID |
| `-TenantId` | Yes | — | Azure Entra tenant ID |
| `-ResourceGroup` | Yes | — | Arc-enabled servers resource group |
| `-Location` | Yes | — | Azure region (always `uksouth`) |
| `-ServicePrincipalId` | Yes | — | Arc onboarding SPN client ID |
| `-ServicePrincipalSecret` | Yes | — | Arc onboarding SPN client secret |
| `-SiteName` | No | *(hostname)* | Trust name, hyphen-separated, no spaces; used to build Arc resource name |
| `-ODSCode` | No | *(hostname)* | ODS code; used to build Arc resource name |
| `-Instance` | No | `01` | Zero-padded instance number; used to build Arc resource name |
| `-NHSRegion` | No | *(not set)* | NHS region code |
| `-SiteType` | No | `static` | `static` or `mobile` |
| `-DeploymentRing` | No | `ring0` | Rollout ring (`ring0`–`ring4`) |

---

## Troubleshooting

### Arc agent fails to connect

Check `C:\ArcSetup\ArcSetup.log` on the VM. Common causes:

- **Firewall blocking outbound** — confirm the VM can reach `*.arc.azure.com` on port 443
- **SPN credentials wrong** — confirm the one-time secret shared before the call has not expired (1-day validity); generate a new one and retry if needed
- **VM already registered** — if the machine was previously connected under a different name, disconnect first: `azcmagent disconnect`

### Script execution blocked

If you see `running scripts is disabled on this system`, run this first in the same elevated session:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

If the script was downloaded from the internet and is still blocked (error: `file is not digitally signed`), unblock the zone restriction first:

```powershell
Unblock-File -Path .\arc-setup.ps1
```

If the script is still blocked after `Unblock-File` (e.g. due to a stricter machine policy), use `Unrestricted` instead — still scoped to the current process only:

```powershell
Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope Process
```

### Onboarding fails: service principal not authorised to onboard machines

The onboarding SPN needs the **Azure Connected Machine Onboarding** role on the spoke subscription. Check and assign via: Subscription → **Access control (IAM)** → Add role assignment → role `Azure Connected Machine Onboarding` → member `spn-azure-arc-onboarding-screening-<env>`. Allow a few minutes for propagation, then rerun the script. (This blocked the first production onboarding.)

### Onboarding fails: resource providers not registered

The spoke subscription must have the **`Microsoft.HybridCompute`** and **`Microsoft.HybridConnectivity`** resource providers registered. Check via: Subscription → **Resource providers** → search each → Register. Then rerun the script.

### Arc machine shows as Disconnected after onboarding

The agent may have lost connectivity. Check:

```powershell
azcmagent show
```

If disconnected, re-run the script. It is safe to re-run — the agent will reconnect and update tags.

### Hybrid Connection not created after Terraform run

The Arc machine must appear in the resource group before Terraform can create the HC. Confirm the machine is **Connected** in the portal (Step 2 verify), then re-run the pipeline.

### Deploy pipeline hangs with no output after the ring banner

The deploy job prints the `--- Ring: … ---` banner and then goes silent for 30+ minutes. Possible causes:

1. **The VM is powered off or asleep.** `az connectedmachine show -n <machine> -g <rg> --query status` — anything other than **Connected** means run commands queue indefinitely against an absent machine.
2. **Stale run commands blocking the queue.** Run commands execute serially per machine, and diagnostic commands accumulate as persistent resources. `az connectedmachine run-command list -o table` — delete anything stuck in a non-terminal state.

### Gateway services not starting after deploy

Check the deployment log on the VM:

```powershell
Get-ChildItem "C:\Program Files\NHS\ManageBreastScreeningGateway\logs\deployments\deploy-*" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1 |
    ForEach-Object { Get-Content $_.FullName }
```
