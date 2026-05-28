# Rubie Gateway Security Guidance for Breast Screening Offices

**Audience:** Hospital IT, network, and information security teams hosting the NHS Rubie Gateway (Run Breast Screening in England) on a VM in the BSO's network.
**Scope:** Covers the gateway VM, its network exposure, the data it holds, and its communications with Azure (Rubie) and on-site modalities.
**Out of scope**: physical datacentre security, hospital-wide identity systems, and the Rubie Azure tenant itself (managed by NHS England).

## 1. Architecture summary

The gateway is an application stack running on a hospital-provided VM, enrolled into Azure via **Azure Arc**. It exposes:

- **Inbound DICOM** (on the agreed DICOM port – typically the IANA-registered 104 or 11112) from a small, named set of on-site mammography modalities.
- **Outbound HTTPS (443)** to Azure Relay (Rubie → Gateway commands) and the Rubie API (Gateway → Rubie events, image uploads).

It stores transient state in local SQLite databases:

- `worklist.db` – Modality Worklist (MWL) entries (patient ID, name, DOB, accession number, scheduled procedure).
- `pacs.db` — short-lived DICOM files.

No long-term patient record is stored on the gateway VM. The source of truth for this lives in Rubie (Azure).

## 2. Network controls

### 2.1 Inbound

- **Allow the agreed DICOM port (typically 104 or 11112) inbound only from the specific IP addresses of the modalities** authorised to send to this gateway. Block from all other sources, including the wider hospital network.
- The gateway will additionally enforce an **AE Title + source IP allowlist** at the application layer (planned — currently in development).
- **No other inbound ports** should be reachable from the hospital network.

### 2.2 Outbound

Allow outbound HTTPS (443) only to:

- `*.servicebus.windows.net` — Azure Relay (Rubie ↔ Gateway).
- Rubie API FQDN (e.g. `manbrs-*.azurewebsites.net` — confirm against the deployed environment).
- Azure Arc control-plane endpoints — see [Microsoft's published list](https://learn.microsoft.com/azure/azure-arc/servers/network-requirements).
- OS update endpoints (Microsoft Update / distro repositories).
- GitHub release endpoints (`github.com`, `*.githubusercontent.com`) — used by Arc to fetch new gateway versions. **[TBC with DevOps: depends on whether release assets are pulled by the Arc agent on the VM, or repackaged Azure-side and pushed via the Arc control plane.]**

Deny all other outbound traffic.

### 2.3 Segmentation

Place the gateway VM on a **dedicated VLAN** or segment, isolated from:

- Clinical workstations.
- The hospital PACS.
- General hospital user devices.

Only the named modalities should be able to reach the gateway on the DICOM port.

## 3. Identity, access, and filesystem

### 3.1 Local accounts

- The gateway application runs under the local **SYSTEM** account. This is a non-interactive account and cannot be used to log in.
- **Interactive logon** to the VM is restricted via Active Directory / local group policy to a named group of hospital administrators. Because SYSTEM is highly privileged on the local machine, controlling who can log in to the VM is the primary access control.

### 3.2 Filesystem permissions

- The SQLite databases (`worklist.db`, `pacs.db`) must be readable/writable **only by the gateway service account**.
- Application and audit logs should similarly be restricted to the service account and a read-only auditors group.

### 3.3 Disk encryption

- Enable encryption on the VM's data disk, as the SQLite databases hold patient-identifiable data.

## 4. Communications with Rubie

### 4.1 Azure Relay (Rubie → Gateway commands)

- The gateway listens on an Azure Relay Hybrid Connection. The connection is **TLS-encrypted end to end** by Azure.
- Relay authentication uses the VM's **Managed Identity** (granted via Arc onboarding). No shared keys or SAS tokens are held on the VM.

### 4.2 Rubie API (Gateway → Rubie)

- All Gateway → Rubie API calls use **HTTPS** with TLS 1.2+ and authenticate with an **Azure Managed Identity** issued by Arc. No bearer tokens or API keys are held on the VM.
- The Rubie API enforces authorisation: the gateway can only act against appointments associated with its configured `Relay`/`Gateway` records.

## 5. Azure Arc deployment

- Arc onboarding is performed by running an enrolment script supplied by NHS England's DevOps team.
- After onboarding, the VM has a **system-assigned Managed Identity**; no shared secrets are needed for Arc-managed services.
- Enable only the Arc extensions actually required (Update Management, Defender for Servers, Azure Monitor Agent). Each extension is a privileged surface — keep the set minimal.
- Apply **Azure Policy** assignments (provided by NHS England) so compliance drift is detected centrally.

## 6. Patching and vulnerability management

- **OS patches:** apply within hospital's standard patching SLA.
- **Gateway application:** NHS England publishes new versions as GitHub releases. Arc fetches and deploys the latest release to the VM. The hospital is not responsible for building or packaging the application.

## 7. Change management

- VM-level changes (firewall rules, AD group membership, OS updates outside normal patching) go through the hospital's change management process.
- Application changes (new gateway releases, configuration updates) are deployed by NHS England via Arc and announced in advance. The hospital should validate inbound DICOM traffic continues to flow after each rollout.
