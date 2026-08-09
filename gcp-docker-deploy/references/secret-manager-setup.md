# Secret Manager wiring

Runtime config — API keys, DB passwords, app-level login credentials — belongs in Secret Manager, referenced by name at deploy time, never baked into the image and never committed. This file covers creating secrets and the IAM binding that's easy to get half-right.

## Creating a secret

```bash
echo -n "<SECRET_VALUE>" | gcloud secrets create <SECRET_NAME> \
  --project="<PROJECT_ID>" --replication-policy="automatic" --data-file=-
```

Check for existing secrets before creating (idempotent setup scripts should skip creation if the secret already exists, and print the update command instead):

```bash
gcloud secrets describe <SECRET_NAME> --project="<PROJECT_ID>" >/dev/null 2>&1 && echo "exists" || echo "missing"
```

## Updating a secret's value (new version, doesn't touch history)

```bash
echo -n "<NEW_VALUE>" | gcloud secrets versions add <SECRET_NAME> \
  --project="<PROJECT_ID>" --data-file=-
```

A `:latest` reference in a Cloud Run deploy or a VM startup script's fetch call picks this up on the *next* deploy/reboot — it doesn't retroactively update anything already running.

## The two-service-account grant that's easy to get backwards

There are two service accounts in play, and each needs a *different* thing:

- **Runtime SA** (attached to the running Cloud Run service or VM): needs `roles/secretmanager.secretAccessor` so the running app can actually read the secret's value.
  ```bash
  gcloud secrets add-iam-policy-binding <SECRET_NAME> \
    --project="<PROJECT_ID>" \
    --member="serviceAccount:<RUNTIME_SA_EMAIL>" \
    --role="roles/secretmanager.secretAccessor"
  ```
  Do this per-secret for least privilege, or grant it at the project level (`gcloud projects add-iam-policy-binding`) if the runtime SA is dedicated to this one app and reading every secret it might need is fine.

- **Deployer SA** (used by GitHub Actions): does **not** need `secretmanager.secretAccessor` at all — it never reads secret values directly. What it needs instead is permission to *set* the runtime SA on the thing it's deploying, which is a completely different grant:
  ```bash
  gcloud iam service-accounts add-iam-policy-binding <RUNTIME_SA_EMAIL> \
    --project="<PROJECT_ID>" \
    --member="serviceAccount:<DEPLOYER_SA_EMAIL>" \
    --role="roles/iam.serviceAccountUser"
  ```
  Without this, `deploy-cloudrun`'s `--service-account=<RUNTIME_SA_EMAIL>` flag (or the VM equivalent) fails with a permission error. The error message references the deploy action, not IAM impersonation, which is why this is easy to misdiagnose as a Cloud Run problem when it's actually a missing `serviceAccountUser` grant on the runtime SA.

## Referencing secrets in a Cloud Run deploy

```yaml
- uses: google-github-actions/deploy-cloudrun@v2
  with:
    secrets: |
      <ENV_VAR_NAME_1>=<SECRET_NAME_1>:latest
      <ENV_VAR_NAME_2>=<SECRET_NAME_2>:latest
```

Each line mounts one secret as one environment variable inside the container. `:latest` always resolves to the most recent version — pin to a specific version number only if you deliberately need to freeze a value across deploys.

## Referencing secrets on a VM

There's no equivalent managed mechanism — the VM's startup script fetches the secret itself via the metadata server + Secret Manager REST API and writes it into a local `.env` file that the container reads via `--env-file`. See the startup script example in `vm-deploy.md`.
