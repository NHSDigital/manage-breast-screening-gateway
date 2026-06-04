# Create an environment

This is the initial manual process to create a new Azure environment (e.g. `dev`, `preprod`, `prod`).

All commands assume you are authenticated to Azure via `az login` and are running from the root of this repository unless stated otherwise.

## Prerequisites

- Owner role on both the hub and spoke Azure subscriptions
- Access to Azure DevOps project `manage-breast-screening-gateway` at `https://dev.azure.com/nhse-dtos`
- Access to the GitHub repository `NHSDigital/manage-breast-screening-gateway`
- Access to an Azure Virtual Desktop (AVD) session connected to the internal network

## Azure resource providers

The following resource providers must be registered on the **spoke subscription** before running Terraform. Missing registrations will cause obscure errors during `terraform apply`.

Run these once per subscription:

```bash
az provider register --namespace Microsoft.HybridCompute
az provider register --namespace Microsoft.GuestConfiguration
az provider register --namespace Microsoft.HybridConnectivity
az provider register --namespace Microsoft.Relay
az provider register --namespace Microsoft.PolicyInsights
az provider register --namespace Microsoft.Insights
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.ManagedIdentity
```

Verify registration status (wait until all show `Registered`):

```bash
az provider show --namespace Microsoft.HybridCompute --query registrationState -o tsv
az provider show --namespace Microsoft.HybridConnectivity --query registrationState -o tsv
az provider show --namespace Microsoft.GuestConfiguration --query registrationState -o tsv
```

## Entra ID

- Create Entra ID group in the `Digital screening` Administrative Unit:
  - `screening_mbsgw_[environment]`

- Ask CCOE to assign the following roles to `mi-mbsgw-[environment]-adotoaz-uks`:
  - [Form for PIM](https://nhsdigitallive.service-now.com/nhs_digital?id=sc_cat_item&sys_id=28f3ab4f1bf3ca1078ac4337b04bcb78&sysparm_category=114fced51bdae1502eee65b9bd4bcbdc)
  - Role Names: `Group.Read.All` and `Directory Readers`
  - Application Name: `mi-mbsgw-[environment]-adotoaz-uks`
  - Managed Identity: `mi-mbsgw-[environment]-adotoaz-uks`
  - Description: Required to resolve the Arc onboarding service principal by display name during Terraform runs

- Confirm the Arc onboarding service principal exists:
  - Name: `spn-azure-arc-onboarding-screening-[environment]`
  - If it does not exist, raise a request with the platform team to create it

- Confirm the web API enterprise application exists:
  - Name: `spn-manbrs-web-api-[environment]`
  - If it does not exist, raise a ServiceNow request for the platform team to create it — the `resource-group-init` Bicep deployment and the `assign_arc_app_roles.sh` script both depend on it
  - [Form for ServiceNow](https://nhsdigitallive.service-now.com/nhs_digital?id=sc_cat_item&sys_id=28f3ab4f1bf3ca1078ac4337b04bcb78&sysparm_category=114fced51bdae1502eee65b9bd4bcbdc)

## Code

- Create the configuration files in `infrastructure/environments/[environment]/`:
  - `variables.sh` — Azure subscription names, hub subscription, ADO pool, soft delete flag
  - `variables.tfvars` — Terraform variable overrides (can be empty if all defaults apply)
- Add an `[environment]:` target in `scripts/terraform/terraform.mk` following the existing pattern
- Add `[environment]` to the `environments` list in the `deploy-stage` step of `.github/workflows/cicd-2-main-branch.yaml`

## Bicep (resource group initialisation)

> [!IMPORTANT]
> This step creates the Azure infrastructure that Terraform depends on — managed identities, Terraform state storage, Key Vault, and resource groups. It must be completed before running Terraform.
> **Required**: Owner role on both the hub and spoke subscriptions.

From an AVD session:

1. Login with Microsoft Graph scope:

   ```bash
   az login --scope https://graph.microsoft.com//.default -t HSCIC365.onmicrosoft.com
   ```

2. Run the Bicep deployment:

   ```bash
   make [environment] resource-group-init
   ```

This deploys two Bicep templates:

**Hub subscription** (`main.bicep`) creates:

- Managed identity `mi-mbsgw-[environment]-adotoaz-uks` — used by ADO to deploy Azure resources via Terraform
- Managed identity `mi-mbsgw-[environment]-ghtoado-uks` — used by GitHub Actions to trigger ADO pipelines (OIDC federated)
- Terraform state storage account `sambsgw[environment]tfstate` with private endpoint
- Infra Key Vault `kv-mbsgw-[environment]-inf` with private endpoint
- Reader role assigned to `mi-mbsgw-[environment]-ghtoado-uks` at hub subscription scope

**Spoke subscription** (`core.bicep`) creates:

- Resource group `rg-mbsgw-[environment]-uks-arc-enabled-servers` — where Arc machines register
- Contributor, RBAC Administrator (delegated), and Resource Policy Contributor roles for `mi-mbsgw-[environment]-adotoaz-uks`
- Contributor and Key Vault Secrets Officer roles for the `screening_mbsgw_[environment]` Entra ID group

Note the outputs printed at the end of the deployment — you will need the managed identity client IDs in subsequent steps.

## Azure DevOps

### ADO group

- Navigate to **Project Settings → Permissions → New group**
- Name: `Run pipeline - [environment]`
- Members: `mi-mbsgw-[environment]-ghtoado-uks`
  - There may be more than one identity with a similar name — check the client ID printed below the name matches the one from the Bicep output
- Permissions (at project level):
  - View project-level information

### ADO pipelines

Create two pipelines, applying the same security settings to each:

**Infrastructure pipeline** — deploys Arc infrastructure via Terraform:

- Navigate to **Pipelines → New pipeline**
- Source: Azure Repos Git → select this repository
- Existing Azure Pipelines YAML file: `.azuredevops/pipelines/deploy.yml`
- Name: `Deploy to Azure - [environment]`
- Do not run yet

**App pipeline** — deploys the gateway app to Arc machines:

- Navigate to **Pipelines → New pipeline**
- Source: Azure Repos Git → select this repository
- Existing Azure Pipelines YAML file: `.azuredevops/pipelines/deploy-app.yml`
- Name: `Deploy Gateway App - [environment]`
- Do not run yet

For each pipeline, manage security:

- Navigate to the pipeline → **⋮ → Manage security**
- Add group: `Run pipeline - [environment]`
- Grant permissions:
  - Edit queue build configuration
  - Queue builds
  - View build pipeline
  - View builds

### ADO service connection

> [!NOTE]
> If the Managed Identity dropdown is empty (common with guest accounts), use the **create manually** link and enter the values directly.

- Navigate to **Project Settings → Service connections → New service connection**
- Connection type: `Azure Resource Manager`
- Authentication method: `Workload Identity Federation (manual)`
- Issuer: `https://token.actions.githubusercontent.com`
- Subject identifier: `repo:NHSDigital/manage-breast-screening-gateway:environment:[environment]`
- Enter the following (from the Bicep output or by running the commands below):

```bash
# Client ID and tenant ID of mi-mbsgw-[environment]-adotoaz-uks
az identity show --name mi-mbsgw-[environment]-adotoaz-uks \
  --resource-group rg-mi-[environment]-uks \
  --subscription "[hub-subscription-name]" \
  --query "{clientId: clientId, tenantId: tenantId}" -o json

# Spoke subscription ID
az account show --subscription "[spoke-subscription-name]" --query id -o tsv
```

- Scope level: `Subscription`
- Subscription ID: `[spoke-subscription-id]`
- Subscription name: `[spoke-subscription-name]`
- Resource group for service connection: leave blank
- Service connection name: `mbsgw-[environment]`
- Do **NOT** tick: Grant access permission to all pipelines

Manage service connection security:

- Navigate to the service connection → **⋮ → Security**
- Add both `Deploy to Azure - [environment]` and `Deploy Gateway App - [environment]` pipelines with permission to use the connection

### ADO environment

- Navigate to **Pipelines → Environments → New environment**
- Name: `[environment]`
- Resource: None
- Set exclusive lock (all environments except `review`)
- Add pipeline permission for both `Deploy to Azure - [environment]` and `Deploy Gateway App - [environment]`

## GitHub

- Create a GitHub environment named `[environment]`:
  - Navigate to **Settings → Environments → New environment**

- Add protection rules (all environments except `review`):
  - Deselect `Allow administrators to bypass configured protection rules`
  - In `Deployment branches and tags` choose `Selected branches and tags`
  - Click `Add deployment branch or tag rule` and enter `main`

- Add the following environment secrets (values from `mi-mbsgw-[environment]-ghtoado-uks`):

```bash
# AZURE_CLIENT_ID — client ID of mi-mbsgw-[environment]-ghtoado-uks
az identity show --name mi-mbsgw-[environment]-ghtoado-uks \
  --resource-group rg-mi-[environment]-uks \
  --subscription "[hub-subscription-name]" \
  --query clientId -o tsv

# AZURE_TENANT_ID
az account show --query tenantId -o tsv

# AZURE_SUBSCRIPTION_ID — hub subscription ID (where the managed identity has Reader)
az account show --subscription "[hub-subscription-name]" --query id -o tsv
```

| Secret                 | Value                                             |
| ---------------------- | ------------------------------------------------- |
| `AZURE_CLIENT_ID`      | Client ID of `mi-mbsgw-[environment]-ghtoado-uks` |
| `AZURE_TENANT_ID`      | Azure tenant ID                                   |
| `AZURE_SUBSCRIPTION_ID` | Hub subscription ID                              |

## First run

1. Merge a pull request to `main` to trigger the CI/CD pipeline, or trigger the ADO pipeline manually from Azure DevOps
2. On the first run you will be prompted to authorise in ADO:
   - Service connection access by the pipeline
   - Agent pool access by the environment
3. Check the pipeline completes successfully — Terraform will create:
   - Arc-enabled server RBAC assignments
   - Azure Relay hybrid connections (empty on first deploy — populated as Arc machines onboard)
   - Log Analytics workspace and Data Collection Rule
   - Azure Monitor policy assignments and remediation tasks

## Arc machine discovery

Terraform automatically discovers Arc machines registered in the Arc-enabled servers resource group and creates a relay Hybrid Connection for each one. On first deploy the resource group is empty, so no connections are created. After each Arc machine is onboarded at a hospital site, run `terraform apply` to pick it up:

```bash
make [environment] terraform-apply
```

After Terraform provisions the Hybrid Connection, re-run `resource-group-init` to assign the `Gateway.Access` app role to the new machine's managed identity:

```bash
make [environment] resource-group-init
```

> **Why is this a separate step?** The pipeline managed identity cannot create app role assignments — `AppRoleAssignment.ReadWrite.All` is required in application auth context regardless of SP ownership, and this permission is not permitted under the organisation's Entra policy. Running `resource-group-init` under a user account with ownership of `spn-manbrs-web-api-[environment]` is sufficient. Without this step the gateway will fail to authenticate against the cloud web API. See [Onboard Hospital VM — Step 4](../runbooks/onboard-hospital-vm.md#step-4--grant-api-access).
