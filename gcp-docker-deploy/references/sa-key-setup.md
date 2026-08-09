# Service account JSON key — the non-preferred alternative

Use this only when standing up WIF isn't practical right now (no IAM admin access yet, a quick prototype that will be redone properly later, etc.). It's real and it works — it's just a long-lived credential, which means:

- It has to be **rotated manually**. Nothing expires it automatically the way a WIF-issued token expires itself.
- If it ever leaks (committed by accident, exfiltrated from a compromised runner, pasted somewhere public), it's a standing credential an attacker can use until someone notices and revokes it — there's no automatic short-lived-token safety net.
- Migrating to WIF later means re-doing the trust setup anyway, so if there's any realistic chance this deployment matters for more than a few weeks, doing WIF from the start (see `wif-setup.md`) is usually less total work than key rotation discipline over the project's life.

## Setup

```bash
gcloud iam service-accounts create "<APP_NAME>-deployer" \
  --project="<PROJECT_ID>" --display-name="GitHub Actions deployer for <APP_NAME>"

DEPLOYER_SA="<APP_NAME>-deployer@<PROJECT_ID>.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "<PROJECT_ID>" \
  --member="serviceAccount:${DEPLOYER_SA}" --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding "<PROJECT_ID>" \
  --member="serviceAccount:${DEPLOYER_SA}" --role="roles/run.admin"   # or the VM-path roles from vm-deploy.md

# Generate the key — do this on a machine you trust, never in CI
gcloud iam service-accounts keys create "./deployer-key.json" \
  --iam-account="${DEPLOYER_SA}"
```

Immediately after generating the key:

```bash
gh secret set GCP_SA_KEY --repo <OWNER>/<REPO> < ./deployer-key.json
rm ./deployer-key.json
```

Don't leave the key file sitting on disk, don't commit it (check `.gitignore` covers `*.json` key files or the specific filename before this step, not after), and don't paste its contents into chat, a ticket, or a doc.

## The workflow-side auth step

```yaml
steps:
  - id: auth
    uses: google-github-actions/auth@v2
    with:
      credentials_json: ${{ secrets.GCP_SA_KEY }}
  - uses: google-github-actions/setup-gcloud@v2   # needed for gcloud CLI commands after auth
```

No `id-token: write` permission needed for this path (that's a WIF-specific requirement) — but keep `contents: read` and whatever else the job needs.

## Rotating the key

```bash
gcloud iam service-accounts keys create "./new-deployer-key.json" --iam-account="${DEPLOYER_SA}"
gh secret set GCP_SA_KEY --repo <OWNER>/<REPO> < ./new-deployer-key.json
rm ./new-deployer-key.json

# List existing keys, then delete the old one once the new one is confirmed working
gcloud iam service-accounts keys list --iam-account="${DEPLOYER_SA}"
gcloud iam service-accounts keys delete <OLD_KEY_ID> --iam-account="${DEPLOYER_SA}"
```

Do this on a schedule (e.g. quarterly) rather than only reactively — the whole point of avoiding WIF's automatic expiry is being replaced by a manual process, so the manual process has to actually happen.
