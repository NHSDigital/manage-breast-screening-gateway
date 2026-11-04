# Spike: interactive access to Arc-enabled gateway VMs

> **Status**: draft spike report. Items marked _(verify)_ are not yet confirmed
> against the Microsoft docs or tested on a real gateway.

## Problem

Support needs to connect to registered gateways to troubleshoot or help users.
`az connectedmachine run-command` works but is slow and not interactive. The
gateways are Arc-enabled in the **trust's** Entra tenant, not ours, and we do not
hold the VM credentials.

## Answers so far

| Question | Answer |
|---|---|
| Can we connect interactively? | Yes |
| Without the trust's local credentials? | No — see [Authentication](#authentication) |
| Command line? | Yes: PowerShell (run command) or SSH, if OpenSSH Server is installed |
| Windows (GUI) session? | Yes, via Windows Admin Center, if set up correctly |
| Multiple concurrent users? | Not confirmed. OpenSSH supports multiple sessions; Windows Admin Center limits _(verify)_ |
| Separate software licence? | Believed not. SSH and Windows Admin Center are included; Arc connectivity features carry no extra charge _(verify)_ |
| Client/server version requirements? | Client: Azure CLI with the `ssh` extension. Server: Arc agent and OpenSSH Server; minimum Windows Server version _(verify)_ |

## Options

| # | Option | Interactive | Needs on VM | Needs from the trust | Notes |
|---|---|---|---|---|---|
| 1 | `az connectedmachine run-command` (today) | No | Arc agent | Azure RBAC on the machine | Slow, one-shot commands |
| 2 | `az ssh arc` with a local user | Yes | OpenSSH Server, `sshd` auto-start, local user | Local user credentials, or someone to create one | Proven in the dev demo — see the [SSH runbook](../runbooks/ssh-to-arc-enabled-vm.md) |
| 3 | `az ssh arc` with Entra ID login | Yes | As option 2, plus Entra login extension | RBAC role assignment in the trust tenant | Not usable unless the trust grants our identities access to their tenant |
| 4 | Windows Admin Center (portal or AVD) | Yes (GUI) | Arc agent, Admin Center set up | Local admin credentials, or Entra RBAC | Used in the demo to create the local user |
| 5 | RDP | Yes (GUI) | RDP enabled and reachable | Network path and credentials | Existing manual route; not via Arc |

## Authentication

Whichever option is used, the VM sees an identity it trusts. Because the gateway
is registered to the trust's tenant, our Entra identities are not trusted by
default. In practice this means one of:

1. **Trust creates and shares a local support account** (option 2/4). Simple, but
   it needs credential handling and rotation.
2. **Trust grants our users access via Azure RBAC / guest accounts** (option 3).
   Better audit trail, more onboarding effort.
3. **Support only works alongside a trust admin** who runs commands or shares a session.

Recommendation: decide this with the trust's security team before building anything
more. Option 2 is the quickest to enable; option 3 is the better long-term shape.

## Demo (dev environment)

Done on `mbsgw-dev`:

1. PIM to the GW resource group, core application subscription and Hub.
2. Sign in to the non-live AVD.
3. Create a custom role and assign it to yourself at subscription level _(details to follow)_.
4. Open Windows Admin Center, sign in as `arcadmin` (password reset needed), and create a local user.
5. Install OpenSSH Server and set `sshd` to start automatically.
6. Connect: `az ssh arc --subscription <sub> --resource-group rg-mbsgw-dev-uks-arc-enabled-servers --name mbsgw-dev --local-user testuser`

Full steps: [SSH to an Arc-enabled VM](../runbooks/ssh-to-arc-enabled-vm.md).

## Open questions

- Which custom role and permissions are the minimum needed?
- Concurrent session limits for SSH and Windows Admin Center.
- Minimum Windows Server and Arc agent versions.
- Is OpenSSH Server acceptable to the trust's security policy, and could it be part of the VM build?
- Where would credentials be stored and who rotates them?
- Audit: are SSH sessions logged anywhere we can review?
