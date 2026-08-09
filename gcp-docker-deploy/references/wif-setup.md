# Workload Identity Federation setup

The point of WIF: GitHub Actions never holds a GCP credential at rest. At run time, the job presents its own short-lived GitHub OIDC token, GCP verifies it against a trust configuration, and hands back a short-lived access token scoped to one impersonated service account. Nothing to leak, nothing to rotate.

## Check before creating anything

A Workload Identity Pool + Provider is a project-level resource, not a per-repo one. If this GCP project has *any* existing GitHub Actions deployment, a pool/provider probably already exists and scopes trust broadly (e.g. to the whole GitHub org via `assertion.repository_owner`) rather than to one repo. Check first:

```bash
gcloud iam workload-identity-pools list --location=global --project=<PROJECT_ID>
gcloud iam workload-identity-pools providers list \
  --workload-identity-pool=<POOL_NAME> --location=global --project=<PROJECT_ID>
gcloud iam workload-identity-pools providers describe <PROVIDER_NAME> \
  --workload-identity-pool=<POOL_NAME> --location=global --project=<PROJECT_ID> \
  --format="value(attributeCondition)"
```

If an existing provider's `attributeCondition` already covers this repo's owner/org, **reuse it** — don't create a second pool for the same trust boundary. Repo-level restriction happens on the *service account's* IAM binding (below), not by making a new provider per repo.

## Create a pool + provider (only if none suitable exists)

```bash
gcloud iam workload-identity-pools create "<POOL_NAME>" \
  --project="<PROJECT_ID>" --location="global" \
  --display-name="GitHub Actions pool"

gcloud iam workload-identity-pools providers create-oidc "<PROVIDER_NAME>" \
  --project="<PROJECT_ID>" --location="global" \
  --workload-identity-pool="<POOL_NAME>" \
  --display-name="GitHub provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == '<GITHUB_ORG_OR_USER>'" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

## Create the deployer service account and bind trust to it

This is the step that actually restricts *which repo* can impersonate *which* service account — do this per app/service, even if the pool/provider is shared project-wide.

```bash
gcloud iam service-accounts create "<APP_NAME>-deployer" \
  --project="<PROJECT_ID>" --display-name="GitHub Actions deployer for <APP_NAME>"

DEPLOYER_SA="<APP_NAME>-deployer@<PROJECT_ID>.iam.gserviceaccount.com"

# Grant the roles this deploy actually needs — Cloud Run example:
gcloud projects add-iam-policy-binding "<PROJECT_ID>" \
  --member="serviceAccount:${DEPLOYER_SA}" --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding "<PROJECT_ID>" \
  --member="serviceAccount:${DEPLOYER_SA}" --role="roles/run.admin"

# The binding that actually scopes WIF trust to ONE repo:
gcloud iam service-accounts add-iam-policy-binding "${DEPLOYER_SA}" \
  --project="<PROJECT_ID>" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_NAME>/attribute.repository/<GITHUB_OWNER>/<GITHUB_REPO>"
```

`<PROJECT_NUMBER>` (not `<PROJECT_ID>`) is required in the `principalSet://` resource path — get it with `gcloud projects describe <PROJECT_ID> --format='value(projectNumber)'` if you don't have it handy.

## GitHub-side secrets

```bash
gh secret set GCP_PROJECT_ID --repo <OWNER>/<REPO> --body "<PROJECT_ID>"
gh secret set GCP_DEPLOYER_SA --repo <OWNER>/<REPO> --body "<APP_NAME>-deployer@<PROJECT_ID>.iam.gserviceaccount.com"
gh secret set GCP_WIF_PROVIDER --repo <OWNER>/<REPO> \
  --body "projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_NAME>/providers/<PROVIDER_NAME>"
```

## The workflow-side auth step

Every job that needs GCP access does this — note `permissions.id-token: write` is required at the job level or the auth step fails with an unhelpful error about missing OIDC token:

```yaml
permissions:
  contents: read
  id-token: write

steps:
  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
      service_account: ${{ secrets.GCP_DEPLOYER_SA }}
      # token_format: access_token   # only needed if a later step (e.g. docker/login-action)
                                      # consumes steps.<id>.outputs.access_token directly;
                                      # deploy-cloudrun manages its own auth session without it
```
