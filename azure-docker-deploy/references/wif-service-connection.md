# Secretless Azure DevOps Service Connection via User-Assigned Managed Identity (WIF)

## Why User-Assigned Managed Identity Instead of `az ad sp create-for-rbac`?

1. `az ad sp create-for-rbac` requires Microsoft Graph API permissions and often fails with `AADSTS530035` under tenant Security Defaults unless re-authenticated with Graph scopes.
2. Client secrets expire and require rotation.
3. **User-Assigned Managed Identity (`Microsoft.ManagedIdentity/userAssignedIdentities`)** is provisioned purely through **Azure Resource Manager (ARM)** (`management.azure.com`) and connects to Azure DevOps via **OpenID Connect (Workload Identity Federation)** — no secrets, no expiration, no Graph API dependency.

---

## Step-by-Step Setup

### 1. Create the User-Assigned Managed Identity & Role Assignment

```powershell
$SUBSCRIPTION_ID = "4496ce24-6036-4f21-b6ae-f5cff32f10d5"
$RG = "rg-<app-name>"
$LOCATION = "japaneast"
$IDENTITY_NAME = "id-<app-name>-cicd"

# Create Managed Identity
$mi = az identity create `
  --name $IDENTITY_NAME `
  --resource-group $RG `
  --location $LOCATION `
  --output json | ConvertFrom-Json

$CLIENT_ID = $mi.clientId
$PRINCIPAL_ID = $mi.principalId
$TENANT_ID = $mi.tenantId

# Grant Contributor role on the target Resource Group
az role assignment create `
  --assignee-object-id $PRINCIPAL_ID `
  --assignee-principal-type ServicePrincipal `
  --role Contributor `
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG" `
  --output json
```

### 2. Create the Azure DevOps Service Connection (`WorkloadIdentityFederation`)

Get the Azure DevOps Project ID:
```powershell
$ORG = "https://dev.azure.com/ConsumerProducts"
$PROJECT = "<project-name>"
$PROJECT_ID = az devops project show --project $PROJECT --org $ORG --query id -o tsv
```

Prepare a JSON configuration file (based on `assets/sc-wif-template.json`) with:
- `subscriptionId`: `4496ce24-6036-4f21-b6ae-f5cff32f10d5`
- `subscriptionName`: `CP-Knowledge`
- `tenantid`: `$TENANT_ID` (`286fdaa8-4b1d-40d1-9a66-15e89c06cef2`)
- `serviceprincipalid`: `$CLIENT_ID`
- `projectReference.id`: `$PROJECT_ID`
- `projectReference.name`: `$PROJECT`
- `name`: `sc-azure-<app-short>`

Create the Service Endpoint and authorize it for all pipelines:
```powershell
$sc = az devops service-endpoint create `
  --service-endpoint-configuration sc.json `
  --org $ORG `
  --project $PROJECT `
  --output json | ConvertFrom-Json

$SC_ID = $sc.id
$ISSUER = $sc.authorization.parameters.workloadIdentityFederationIssuer
$SUBJECT = $sc.authorization.parameters.workloadIdentityFederationSubject

# Authorize all pipelines in the project to use this Service Connection
az devops service-endpoint update `
  --id $SC_ID `
  --enable-for-all true `
  --org $ORG `
  --project $PROJECT `
  --output json
```

### 3. Wire the Federated Identity Credential on the Managed Identity

```powershell
az identity federated-credential create `
  --name "fed-azdo-$PROJECT" `
  --identity-name $IDENTITY_NAME `
  --resource-group $RG `
  --issuer $ISSUER `
  --subject $SUBJECT `
  --audiences "api://AzureADTokenExchange" `
  --output json
```

Now any `AzureCLI@2` task in `azure-pipelines.yml` referencing `azureSubscription: 'sc-azure-<app-short>'` will authenticate automatically via OIDC!
