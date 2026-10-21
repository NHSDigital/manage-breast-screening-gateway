# ADR-008: Access control for the gateway's DICOM listeners

Date: 2026-10-21

Status: Proposed

## Context

The gateway exposes two DICOM listeners on each hospital VM: PACS C-STORE and MWL C-FIND. Until now, both accepted an association from any device that could reach the port. An unrestricted listener means any host on the trust network segment can read worklist data and push images.

Constraints:

- Modalities are trust-owned devices (e.g. Hologic) whose DICOM configuration we influence but do not control; requiring client TLS certificates on them is not currently practical.
- The VMs sit on trust-internal networks behind trust firewalls with no inbound internet connectivity; the threat model is misconfigured or unauthorised devices on the internal network, not internet exposure.
- Per-site configuration reaches the VM as a `.env` file written by the deployment pipeline.

## Decision

Control access with two independent layers:

1. **Calling AE title allowlist in the application.** `PACS_ALLOWED_CALLING_AETS` and `MWL_ALLOWED_CALLING_AETS` set pynetdicom's `require_calling_aet` on the respective server. Associations from unlisted calling AE titles are rejected at the association level. An empty value (the default) accepts any caller, so existing sites are unaffected until configured. Per-site values come from an `AllowedCallingAets` tag (comma-separated) on each Arc machine, which the deployment pipeline reads into the machine's `.env`.

2. **IP scoping at the Windows Firewall.** The inbound rules for the PACS and MWL ports are restricted to the known modality addresses per site (`Set-NetFirewallRule ... -RemoteAddress`). This is an operational task per VM, not application code.

An AE title is a self-declared string, so the allowlist is identification, not authentication – it catches misdirected and misconfigured devices. The firewall provides network-level control but knows nothing about DICOM.

Alternative considered:

- **DICOM TLS (with client certificates)** would provide genuine authentication, but requires certificate support and lifecycle management on trust modalities that we cannot mandate today. Rejected as disproportionate for now.

## Consequences

### Positive Consequences

- A device with the wrong AE title configuration is rejected at association time with a clear reason, instead of silently reading worklist data or storing images.
- Third-party equipment can be granted access explicitly.
- Rollout is per-site and non-breaking.

### Negative Consequences

- AE titles can be spoofed. Network-level control still depends on the firewall rules being applied and maintained per site.
- A site is only protected once both layers are configured; the default is open. Onboarding checklists must include setting the allowlist and scoping the firewall rules.

### Neutral Consequences

- Modality AE titles become per-site configuration data we must keep accurate.
