# SSH to an Arc-enabled gateway VM

> **When to use**: You need a shell on a gateway VM (e.g. `mbsgw-dev`) that is
> Azure Arc-enabled, without RDP. Access is via `az ssh arc` using a local user on the VM.

> **Status**: draft, written from a first walkthrough that involved some trial and
> error. Steps marked _(verify)_ may be missing detail — please correct as you go.

## Prerequisites

- PIM elevation to the gateway resource group, the core application subscription and the Hub.
- Access to the non-live AVD (to reach Windows Admin Center).
- A custom role assigned to you at subscription level _(verify: role name and
  permissions to be documented — e.g. Arc connect/`Microsoft.HybridCompute/machines/*` actions)_.
- Azure CLI with the `ssh` extension: `az extension add --name ssh`.

## 1. Prepare the VM (one-off)

1. PIM up, then log in to the non-live AVD.
2. Open **Windows Admin Center** and sign in as `arcadmin`
   (the password had to be changed on first login).
3. In Windows Admin Center, create a separate **local user** (e.g. `testuser`)
   for SSH sessions — don't use `arcadmin` for day-to-day access.
4. Install **OpenSSH Server** on the Windows VM and set the `sshd` service to start
   automatically:

   ```powershell
   Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
   Set-Service -Name sshd -StartupType Automatic
   Start-Service sshd
   ```

   _(verify: whether the Arc SSH endpoint/port needs enabling on the agent, e.g.
   `azcmagent config set incomingconnections.ports 22`, and whether a firewall rule is needed.)_

## 2. Connect

```bash
az login
az ssh arc \
  --subscription <subscription ID>" \
  --resource-group "rg-mbsgw-dev-uks-arc-enabled-servers" \
  --name "mbsgw-dev" \
  --local-user "testuser"
```

Enter the local user's password when prompted.

## Troubleshooting

- **Permission denied / authorisation errors** — check PIM is active and the custom
  role is assigned at the subscription.
- **Connection refused / timeout** — confirm `sshd` is running and set to Automatic,
  and the Arc agent allows incoming connections on the SSH port.
