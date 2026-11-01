# Provisioning Azure Container Registry (ACR) & Azure Container Apps (ACA)

## 1. Resource Group & Resource Providers

```powershell
$SUBSCRIPTION_ID = "4496ce24-6036-4f21-b6ae-f5cff32f10d5"
$RG = "rg-<app-name>"
$LOCATION = "japaneast"

az account set --subscription $SUBSCRIPTION_ID
az group create --name $RG --location $LOCATION --output json

# Ensure required resource providers are registered
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
```

Verify registration before creating resources:
```powershell
az provider show -n Microsoft.ContainerRegistry --query "registrationState" -o tsv
az provider show -n Microsoft.App --query "registrationState" -o tsv
az provider show -n Microsoft.OperationalInsights --query "registrationState" -o tsv
```

---

## 2. Create ACR & Build Initial Image (with DNS Check)

ACR names must be **globally unique, 5–50 alphanumeric characters only (no hyphens)**.

```powershell
$ACR_NAME = "acr<appnameshort>"
$APP_NAME = "<app-name>"

az acr create `
  --name $ACR_NAME `
  --resource-group $RG `
  --location $LOCATION `
  --sku Basic `
  --admin-enabled true `
  --output json
```

> **Important Gotcha (DNS Propagation)**: Immediately after `az acr create`, Azure internal DNS (`168.63.129.16`) can take 60–120 seconds to resolve `<acr-name>.azurecr.io`. If `az acr build` fails on the push step with `lookup <acr-name>.azurecr.io: no such host`, simply re-run `az acr build` once DNS resolves (cached layers make the retry fast).

```powershell
az acr build `
  --registry $ACR_NAME `
  --resource-group $RG `
  --image "${APP_NAME}:latest" .
```

---

## 3. Create Azure Container Apps Environment & Container App

```powershell
$CAE_NAME = "cae-$APP_NAME"

# Create Container Apps Environment (auto-creates Log Analytics workspace if omitted)
az containerapp env create `
  --name $CAE_NAME `
  --resource-group $RG `
  --location $LOCATION `
  --output json

# Create Container App with External Ingress, Secrets, and Env Vars
az containerapp create `
  --name $APP_NAME `
  --resource-group $RG `
  --environment $CAE_NAME `
  --image "${ACR_NAME}.azurecr.io/${APP_NAME}:latest" `
  --registry-server "${ACR_NAME}.azurecr.io" `
  --ingress external `
  --target-port 8080 `
  --cpu 0.5 `
  --memory 1.0Gi `
  --min-replicas 0 `
  --max-replicas 3 `
  --secrets "gemini-api-key=$GEMINI_API_KEY" "session-secret=$SESSION_SECRET" `
  --env-vars "GEMINI_MODEL=gemini-3.8-flash" "APP_PASSWORD=FTC" "SESSION_HTTPS_ONLY=true" "GEMINI_API_KEY=secretref:gemini-api-key" "SESSION_SECRET=secretref:session-secret" `
  --query "{name:name, fqdn:properties.configuration.ingress.fqdn, provisioningState:properties.provisioningState}" `
  --output json
```

---

## 4. Register the Azure Pipeline

After placing `azure-pipelines.yml` in the repository root:

```powershell
az pipelines create `
  --name "Build and Deploy to Azure Container Apps" `
  --yaml-path azure-pipelines.yml `
  --repository $APP_NAME `
  --repository-type tfsgit `
  --branch main `
  --skip-first-run true `
  --org "https://dev.azure.com/ConsumerProducts" `
  --project $APP_NAME `
  --output json
```
