---
name: azure-docker-deploy
description: Register a repository in Azure DevOps Repos, build Docker images in Azure Container Registry (ACR), and deploy to Azure Container Apps (ACA) via Azure Pipelines with Workload Identity Federation (User-Assigned Managed Identity). Use when asked to register code in Azure DevOps Repos, deploy Dockerized apps to Azure Apps / Container Apps, or set up Azure Pipelines CI/CD.
---

# Azure Docker Deploy (Azure DevOps Repos + ACR + Azure Container Apps)

This skill packages a battle-tested workflow for registering a repository in **Azure DevOps Repos**, provisioning **Azure Container Registry (ACR)** + **Azure Container Apps (ACA)**, and wiring secretless **Azure Pipelines CI/CD** using **Workload Identity Federation (User-Assigned Managed Identity)**.

It solves four common failure modes on Windows and multi-tenant corporate Entra ID environments:
1. **Windows `az login` URL truncation (`AADSTS900144`) & Device Code blocking (`AADSTS530035`)**: Solved by enabling Windows Web Account Manager (`enable_broker_on_windows=true`) and logging in per-tenant.
2. **Multi-tenant split between Azure DevOps and Azure Subscriptions**: Solved by using the Azure DevOps tenant's OAuth token (`499b84ac-1321-427f-aa17-267ca6975798`) for non-interactive `git push` while targeting the Azure Subscription tenant for ARM resource provisioning.
3. **Microsoft Graph API restriction on `az ad sp create-for-rbac` (`AADSTS530035`)**: Solved by creating an ARM-native **User-Assigned Managed Identity (`az identity create`)** and wiring it to an Azure DevOps **Workload Identity Federation** Service Connection — zero Graph API calls, zero client secrets to expire.
4. **Container runtime environment differences (Cloud Run vs. Azure Container Apps)**: Ensuring HTTPS session cookies (`SESSION_HTTPS_ONLY`) detect `CONTAINER_APP_NAME` in addition to `K_SERVICE`, and waiting for ACR DNS propagation before the first image push.

---

## Environment Defaults (Fortience / ConsumerProducts)

Unless the user specifies otherwise, check or confirm these known organizational defaults:
- **Azure DevOps Organization**: `https://dev.azure.com/ConsumerProducts`
  - **Azure DevOps Tenant ID**: `2ad658c1-f79e-4a01-817e-6b83dae3a9aa` (`フォーティエンスコンサルティング株式会社`)
- **Azure Subscription**: `CP-Knowledge` (`4496ce24-6036-4f21-b6ae-f5cff32f10d5`)
  - **Azure Subscription Tenant ID**: `286fdaa8-4b1d-40d1-9a66-15e89c06cef2` (`(CP本部)フォーティエンスコンサルティング`)
- **Default Region**: `japaneast` (東日本)

---

## Step 1 — Authenticate Azure CLI across Tenants (Windows WAM)

Never use `enable_broker_on_windows=false` (truncates `&client_id` in `cmd.exe`) or `--use-device-code` against tenants with Entra Security Defaults enabled (blocks with `AADSTS530035`).

1. Enable WAM (Windows Web Account Manager):
   ```powershell
   az config set core.enable_broker_on_windows=true
   ```
2. Log in to the Azure Subscription tenant (`286fdaa8-4b1d-40d1-9a66-15e89c06cef2`) and select the subscription:
   ```powershell
   az login --tenant 286fdaa8-4b1d-40d1-9a66-15e89c06cef2
   az account set --subscription 4496ce24-6036-4f21-b6ae-f5cff32f10d5
   ```
3. Ensure the Azure DevOps tenant (`2ad658c1-f79e-4a01-817e-6b83dae3a9aa`) also has a valid cached token for `git push` and `az devops`:
   ```powershell
   az account get-access-token --tenant 2ad658c1-f79e-4a01-817e-6b83dae3a9aa --resource 499b84ac-1321-427f-aa17-267ca6975798 --query accessToken -o tsv
   ```
   Full details in `references/azdo-repos-and-auth.md`.

---

## Step 2 — Create Azure DevOps Project / Repo & Configure Git Remote

1. If the project does not exist yet in `https://dev.azure.com/ConsumerProducts`, create it (this automatically initializes a default Git repository with the same name):
   ```powershell
   az devops project create --name <project-name> --org https://dev.azure.com/ConsumerProducts --visibility private --source-control git --output json
   ```
2. If the local repository already has `origin` pointing to GitHub, preserve `origin` and add Azure DevOps as the `azure` remote:
   ```powershell
   git remote add azure https://dev.azure.com/ConsumerProducts/<project-name>/_git/<repo-name>
   ```
3. Push using the Azure DevOps OAuth bearer token (prevents interactive credential manager hangs):
   ```powershell
   $token = az account get-access-token --tenant 2ad658c1-f79e-4a01-817e-6b83dae3a9aa --resource 499b84ac-1321-427f-aa17-267ca6975798 --query accessToken -o tsv
   git -c http.extraheader="AUTHORIZATION: bearer $token" push azure main
   ```

---

## Step 3 — Check App Compatibility for Azure Container Apps

Before building the image, inspect the app's `Dockerfile` and configuration:
1. **Port**: Confirm `EXPOSE 8080` (or the target port) and that the server binds to `0.0.0.0`.
2. **Secure Cookies behind HTTPS Ingress**:
   Azure Container Apps terminates TLS at the ingress proxy and sets `CONTAINER_APP_NAME` automatically inside the container (whereas Cloud Run sets `K_SERVICE`). If the app enables `https_only` session cookies based on `K_SERVICE`, update it to check both:
   ```python
   SESSION_HTTPS_ONLY = os.environ.get(
       "SESSION_HTTPS_ONLY",
       "true" if (os.environ.get("K_SERVICE") or os.environ.get("CONTAINER_APP_NAME")) else "false",
   ).lower() == "true"
   ```
3. **Python `uv` projects**: If using `uv sync --no-install-project`, ensure `ENV PYTHONPATH=/app` is set in `Dockerfile`.

---

## Step 4 — Provision Resource Group, ACR, and Container Apps

See `references/aca-acr-deploy.md` for full commands. Summary:
1. Create a dedicated resource group `rg-<app-name>` in `japaneast`.
2. Ensure resource providers `Microsoft.ContainerRegistry`, `Microsoft.App`, and `Microsoft.OperationalInsights` are `Registered`.
3. Create ACR (`acr<appnameshort>`, alphanumeric only, Basic SKU) and wait ~15–30 seconds for DNS propagation (`Resolve-DnsName <acr-name>.azurecr.io`) before running `az acr build`.
4. Build the initial image with `az acr build --registry <acr-name> --image <app-name>:latest .`.
5. Create Container Apps Environment `cae-<app-name>` and Container App `<app-name>` with `--ingress external --target-port 8080 --cpu 0.5 --memory 1.0Gi --secrets ... --env-vars ...`.

---

## Step 5 — Wire Secretless CI/CD (Managed Identity + WIF + Azure Pipelines)

Do **not** use `az ad sp create-for-rbac` if Graph API is restricted. Instead, use ARM User-Assigned Managed Identity + Workload Identity Federation (`references/wif-service-connection.md`):
1. Create Managed Identity `id-<app-name>-cicd` in `rg-<app-name>`.
2. Assign `Contributor` role on `rg-<app-name>` to the Managed Identity's `principalId`.
3. Create the Azure DevOps Service Connection (`sc-azure-<app>`) using `assets/sc-wif-template.json`.
4. Read `workloadIdentityFederationIssuer` and `workloadIdentityFederationSubject` from the created Service Connection and register them on the Managed Identity with `az identity federated-credential create`.
5. Add `azure-pipelines.yml` (from `assets/azure-pipelines.yml`) to the repository root, register the pipeline via `az pipelines create`, and push to `azure main`.

---

## Step 6 — Verify End-to-End

1. Check the triggered pipeline run until `status == "completed"` and `result == "succeeded"`:
   ```powershell
   az pipelines runs list --org https://dev.azure.com/ConsumerProducts --project <project-name> --output table
   ```
2. Confirm the Container App's active image tag updated and hit `/healthz` (and `/login`):
   ```powershell
   Invoke-RestMethod -Uri "https://<fqdn>/healthz"
   ```
3. Document the Azure Container Apps public URLs and Azure DevOps links in `README.md`.

---

## Reference & Asset Files

- `references/azdo-repos-and-auth.md` — Windows WAM login, multi-tenant token handling, and Azure Repos creation/push commands
- `references/wif-service-connection.md` — Step-by-step ARM Managed Identity + Azure DevOps Workload Identity Federation setup
- `references/aca-acr-deploy.md` — Resource group, provider registration, ACR build (with DNS check), and Container Apps creation
- `assets/azure-pipelines.yml` — Ready-to-use Azure Pipelines YAML template for ACR build & ACA deploy
- `assets/sc-wif-template.json` — Service Endpoint JSON template for `az devops service-endpoint create`
