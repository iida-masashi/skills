# Azure CLI Authentication & Azure DevOps Repos Setup

## 1. Why Standard `az login` or `--use-device-code` Fails on Windows

In corporate Windows environments with multiple Entra ID tenants:
- **`enable_broker_on_windows = false`**: Causes Azure CLI to open the browser via `cmd.exe /c start <url>`, which truncates query parameters after `&` and fails with `AADSTS900144: The request body must contain the following parameter: 'client_id'`.
- **`az login --use-device-code`**: Blocked by Entra ID **Security Defaults** (`AADSTS530035: Access has been blocked by security defaults`) on protected tenants like `(CP本部)フォーティエンスコンサルティング` (`286fdaa8-4b1d-40d1-9a66-15e89c06cef2`).

### Solution: Enable Windows Web Account Manager (WAM)

```powershell
# Enable native Windows account picker (WAM)
az config set core.enable_broker_on_windows=true

# Log in to the Azure Subscription tenant ((CP本部)フォーティエンスコンサルティング)
az login --tenant 286fdaa8-4b1d-40d1-9a66-15e89c06cef2

# Set default subscription (CP-Knowledge)
az account set --subscription 4496ce24-6036-4f21-b6ae-f5cff32f10d5
```

If you also need a token for the Azure DevOps tenant (`2ad658c1-f79e-4a01-817e-6b83dae3a9aa`) and haven't logged into it yet:
```powershell
az login --tenant 2ad658c1-f79e-4a01-817e-6b83dae3a9aa --allow-no-subscriptions
az account set --subscription 4496ce24-6036-4f21-b6ae-f5cff32f10d5
```

---

## 2. Creating an Azure DevOps Project and Repository

```powershell
$ORG = "https://dev.azure.com/ConsumerProducts"
$PROJECT = "<project-name>"

# Configure CLI defaults
az devops configure --defaults organization=$ORG project=$PROJECT

# Create private project with Git source control
# (Automatically creates a default Git repository with the same name as $PROJECT)
az devops project create `
  --name $PROJECT `
  --org $ORG `
  --visibility private `
  --source-control git `
  --output json

# Verify repository URL
az repos list --org $ORG --project $PROJECT --output table
```

If adding a second repository inside an existing project:
```powershell
az repos create --name <repo-name> --org $ORG --project $PROJECT --output json
```

---

## 3. Adding `azure` Remote & Pushing Non-Interactively

When a repository already uses `origin` for GitHub, keep `origin` and add `azure` as a second remote:

```powershell
git remote add azure "https://dev.azure.com/ConsumerProducts/$PROJECT/_git/$PROJECT"
git remote -v
```

To push without triggering an interactive Git Credential Manager popup (or failing when the active Azure CLI subscription belongs to a different tenant), request an Azure DevOps resource token (`499b84ac-1321-427f-aa17-267ca6975798`) explicitly from the Azure DevOps tenant (`2ad658c1-f79e-4a01-817e-6b83dae3a9aa`):

```powershell
$token = az account get-access-token `
  --tenant 2ad658c1-f79e-4a01-817e-6b83dae3a9aa `
  --resource 499b84ac-1321-427f-aa17-267ca6975798 `
  --query accessToken -o tsv

git -c http.extraheader="AUTHORIZATION: bearer $token" push azure main
```
