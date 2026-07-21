# Promote a Gateway VM from Pre-Prod to Prod

> **When to use**: A hospital VM currently running the **pre-prod** gateway needs to become the **prod** gateway (same infrastructure, different environment).
> **Related**: [Onboard Hospital VM](./onboard-hospital-vm.md) | [Cleanup](./cleanup.md) | [Deployment Pipeline](../deployment-pipeline.md)

---

## Why this is not just "re-point the gateway"

Pre-prod and prod are separate Azure subscriptions, with separate Arc resource groups, relay namespaces (`relay-manbrs-<env>`), web-API service principals (`spn-manbrs-web-api-<env>`) and ADO pipelines. An Arc-connected machine belongs to **exactly one** subscription, and the gateway services authenticate using that machine's managed identity. A pre-prod machine identity holds the `Gateway.Access` role on the **pre-prod** API and cannot talk to prod.

So you cannot promote by editing `.env`. The machine must be **disconnected from the pre-prod subscription and re-onboarded into the prod subscription** — effectively the [onboarding runbook](./onboard-hospital-vm.md) run for prod, preceded by a clean decommission of the pre-prod gateway.

> One box hosts one gateway. After this procedure there is **no pre-prod gateway at this site**. If pre-prod is still needed at the site, use a different VM.

---

## Before the day (do these in advance)

- [ ] **You can actually run this.** Check [Onboarding — Who can run this](./onboard-hospital-vm.md#who-can-run-this): PIM for the prod hub and spoke, Owner on `spn-manbrs-web-api-prod`, secret rights on the onboarding SPN. Discovering a missing permission on the day cost the first promotion most of a week.
- [ ] **`GATEWAY_RINGS` is set for prod.** `infrastructure/environments/prod/variables.sh` must set `GATEWAY_RINGS` to include the ring the site is tagged with (for initial production installs this will typically be `ring1`). If it is unset it defaults to `ring0` and the prod deploy pipeline **silently skips** the machine.
- [ ] **Prod infrastructure exists.** Confirm the prod relay namespace, `spn-manbrs-web-api-prod`, Log Analytics workspace and the prod ADO pipelines are provisioned and have had a successful infra deploy.
- [ ] **Prod Manage (Rubie) is seeded.** The prod Rubie instance has the site's clinic/setting, a `Relay` record pointing at `relay-manbrs-prod` and the prod gateway, the `gateway_images` feature flag enabled, and a test appointment for the end-to-end check.
- [ ] **DHCP reservation confirmed** for the VM, so the IP the modality targets cannot change between decommission and go-live.
- [ ] **Modality engineer briefed** that the gateway **AE titles change** (see [Step 5](#step-5--reconfigure-the-modality-on-site)) and the modality must be reconfigured and re-tested on the day.
- [ ] **Fresh prod Arc onboarding SPN secret** created per [Onboarding — Step 0](./onboard-hospital-vm.md#step-0--create-a-temporary-onboarding-secret) — on the day (24h expiry), shared only during the call.

---

## Step 1 — Decommission the pre-prod gateway (on the VM)

Run from an **elevated PowerShell session** on the VM. First confirm you are on the right machine:

```powershell
hostname
Get-Service Gateway-* | Format-Table Name, Status
```

Then run the cleanup script, which stops and removes the services and **removes the installation directory including all pre-prod data** (`worklist.db`, `pacs.db`, `data\storage`):

```powershell
.\scripts\powershell\cleanup.ps1
```

**Verify**: no `Gateway-*` services remain and `C:\Program Files\NHS\ManageBreastScreeningGateway` is gone (see [Cleanup runbook — Verify](./cleanup.md)):

```powershell
Get-Service Gateway-* -ErrorAction SilentlyContinue
Test-Path 'C:\Program Files\NHS\ManageBreastScreeningGateway'   # must be False
```

## Step 2 — Disconnect from the pre-prod Arc subscription

Still on the VM, elevated:

```powershell
azcmagent disconnect
```

This removes the machine's registration from the pre-prod resource group. The Arc **agent stays installed** — only the registration is removed, so re-onboarding in Step 3 skips the agent install.

**Verify**: `azcmagent show` reports the agent as **Disconnected**.

## Step 3 — Re-onboard into prod

This is [Onboarding runbook Step 2](./onboard-hospital-vm.md#step-2--run-arc-onboarding-script-on-the-gateway-vm) with **prod parameters**. The site parameters (`SiteName`, `ODSCode`, `Instance`) are unchanged, so the Arc resource name is identical — but it is now created in the prod resource group.

```powershell
.\arc-setup.ps1 `
    -SubscriptionId         "<prod-spoke-subscription-id>" `
    -TenantId               "<tenant-id>" `
    -ResourceGroup          "rg-mbsgw-prod-uks-arc-enabled-servers" `
    -Location               "uksouth" `
    -ServicePrincipalId     "<arc-onboarding-spn-client-id>" `
    -ServicePrincipalSecret "<prod-arc-onboarding-spn-client-secret>" `
    -SiteName               "Hull-University-Teaching-Hospitals-NHS-Trust" `
    -ODSCode                "RWA" `
    -Instance               "01" `
    -NHSRegion              "neyh" `
    -SiteType               "static" `
    -DeploymentRing         "ring1"
```

**Verify**: in the Azure portal, `rg-mbsgw-prod-uks-arc-enabled-servers` → Azure Arc machines → `gw-<...>-rwa-01` is **Connected**.

## Step 4 — Provision prod and deploy the prod gateway

From here, follow the onboarding runbook against **prod**:

1. **Grant API access** — `make prod assign-arc-app-roles` ([Step 3](./onboard-hospital-vm.md#step-3--grant-api-access)). This assigns `Gateway.Access` on `spn-manbrs-web-api-prod` to the machine's new prod managed identity. The old pre-prod assignment is irrelevant (different identity) and is cleaned up in Step 6.
2. **Provision the Hybrid Connection** — run **Deploy Arc Infrastructure - prod** ([Step 4](./onboard-hospital-vm.md#step-4--trigger-terraform-to-provision-the-hybrid-connection)). Creates `hc-gw-<...>-rwa-01` in `relay-manbrs-prod`.
3. **Deploy the application** — run **Deploy Gateway - prod** with a **released** `releaseTag` (not a pre-prod build) ([Step 5](./onboard-hospital-vm.md#step-5--deploy-the-gateway-application)). This writes a fresh prod `.env` (prod relay namespace, `CLOUD_API_HOSTNAME=manage-breast-screening.nhs.uk`, prod AE titles), fully replacing the pre-prod `.env`.
4. **Update prod Rubie's `Gateway` record with the machine's new identity.** Re-onboarding created a **new managed identity** — the pre-prod OID is dead. Image uploads are authorised against `Gateway.oid`, so until this is updated every upload will be rejected with a 403. Get the new principal ID and set it on the Gateway record in the prod Django admin:

   ```bash
   az connectedmachine show \
     -g rg-mbsgw-prod-uks-arc-enabled-servers \
     -n gw-<site>-<ods>-<instance> \
     --query identity.principalId -o tsv
   ```

   While in the admin, confirm the `Relay` record's **Setting** matches the site's clinics' Setting — a mismatch silently routes every appointment to the manual-images flow.

**Verify**: the [onboarding acceptance criteria](./onboard-hospital-vm.md#step-6--verify-acceptance-criteria) — all four services Running, ports listening, **and the relay log ends with `Connected - waiting for worklist actions...`**. A Running service that never logs `Connected` is not healthy. Do not rely on the Log Analytics heartbeat (VM telemetry export is a known issue at the time of writing). Also confirm the databases start empty:

```powershell
& 'C:\Program Files\NHS\ManageBreastScreeningGateway\current\.venv\Scripts\python.exe' -c "import sqlite3; print('worklist rows:', sqlite3.connect(r'C:\Program Files\NHS\ManageBreastScreeningGateway\data\worklist.db').execute('SELECT count(*) FROM worklist_items').fetchone()[0])"
```

## Step 5 — Reconfigure the modality

The gateway AE titles are environment-specific: the `.env` builder sets `MWL_AET=RUBIE_MWL_<ENV>` / `PACS_AET=RUBIE_PACS_<ENV>`, where the environment is uppercased and truncated to 3 characters if longer than 4.

| Environment | MWL AE title | PACS AE title |
|-------------|--------------|---------------|
| pre-prod (`PREPROD` → `PRE`) | `RUBIE_MWL_PRE` | `RUBIE_PACS_PRE` |
| prod (`PROD`) | `RUBIE_MWL_PROD` | `RUBIE_PACS_PROD` |

The modality is currently configured to send to the **pre-prod** AE titles. The modality's MWL and PACS destinations must be updated to the **prod** AE titles. The VM IP and ports (`104` / `11112`) will typically be unchanged.

**Verify**: a C-ECHO from the modality to each prod AE title succeeds. (A C-ECHO to the old `..._PRE` titles will now fail — expected.)

## Step 6 — Clean up the pre-prod side (Azure)

Disconnecting the machine in Step 2 leaves orphaned pre-prod resources: a disconnected Arc machine, a dangling Hybrid Connection (`hc-gw-<...>-rwa-01` in `relay-manbrs-preprod`), and a stale `Gateway.Access` role assignment.

- [ ] Run **Deploy Arc Infrastructure - preprod** (Terraform) so it destroys the now-orphaned Hybrid Connection.
- [ ] Remove the disconnected Arc machine resource from `rg-mbsgw-preprod-uks-arc-enabled-servers` if Terraform/Arc has not already.
- [ ] Confirm the stale pre-prod app-role assignment is removed (re-running `make preprod assign-arc-app-roles` reconciles, or remove it via the portal).

---

## End-to-end check

With the modality reconfigured and prod Rubie seeded:

1. Restart the relay listener first (`Restart-Service Gateway-Relay`, wait for `Connected - waiting`) so the check runs against a fresh relay connection.
2. Start the seeded test appointment in **prod** Rubie → the Gateway action in the Django admin goes **`confirmed`** within seconds, and the item is in the gateway's `worklist.db`.
3. Query the worklist from the modality → the item appears.
4. Acquire and send images → they arrive in the prod gateway PACS and are forwarded to prod Rubie.
5. Confirm the images appear against the appointment in prod Rubie.

If step 2 fails, the Gateway action's `last_error` names the failing phase — see the [live clinic debugging runbook](./live-clinic-debugging.md) for the symptom → check mapping.

Before the site's first real clinic on the promoted gateway, work through [Clinic preparation](./clinic-preparation.md).

---

## Gotchas

| Symptom | Cause | Fix |
|---------|-------|-----|
| **Deploy Gateway - prod** reports "No machines found for ring1 — skipping" | `GATEWAY_RINGS` not set for prod, defaulting to `ring0` | Set `GATEWAY_RINGS="ring1"` in `prod/variables.sh` and redeploy |
| Services start but fail to authenticate against the cloud API | `Gateway.Access` not assigned to the **prod** managed identity | Run `make prod assign-arc-app-roles` |
| Modality C-ECHO fails after promotion | Modality still targeting `..._PRE` AE titles | Reconfigure modality to `..._PROD` (Step 5) |
| Hybrid Connection not created by Terraform | Arc machine not yet **Connected** in the prod RG | Confirm Step 3 verify, then re-run the infra pipeline |
| Pre-prod relay still shows connection attempts | Orphaned pre-prod HC / registration | Complete Step 6 |
| Rubie check-ins time out with `phase: connecting` while the listener is healthy | Rubie-side network — most likely a **broken relay private endpoint**. Note the PE can blackhole all traffic **while showing Approved** | Delete the PE and let Terraform recreate it, then prove the path with the echo probe from the Rubie container — see [live clinic debugging](./live-clinic-debugging.md) |
| The whole UI runs in manual-images mode | `gateway_images` flag off in the Manage repo's **`flags.production.yml`**, or Relay↔Setting mismatch, or the appointment already has a manual study | Flag change requires a Manage deploy (one-line PR, leave the other flags alone); Setting fix is one field in admin; otherwise use a fresh appointment |
| Image uploads rejected with 403 after promotion | `Gateway.oid` still holds the old pre-prod identity | Step 4.4 — update to the new principal ID |
| Rubie shows the manual-images flow instead of awaiting images | `Relay` record's Setting doesn't match the clinic's Setting, or the appointment already has a manual study | Fix the Setting FK in the admin; retest with a fresh appointment |
| Sends fail after the gateway has been idle overnight | Relay listener connection died silently (known issue) | `Restart-Service Gateway-Relay`; restart before every clinic until the listener liveness fix ships |
