# VM (Compute Engine) deploy — annotated

Real shape: a Container-Optimized OS (COS) VM running two containers on a shared Docker network (an nginx-style frontend proxying to a backend), deployed via SSH-over-IAP from GitHub Actions. Use this when the Cloud Run decision guide in `SKILL.md` says VM.

This path has more moving parts than Cloud Run — you're operating a real machine, even a minimal one — so budget for a one-time setup script plus a startup script, not just a workflow file.

## One-time setup (idempotent scripts, run locally by a human)

### 1. `setup-gcp.sh` — APIs, Artifact Registry, service accounts

Two service accounts, same separation-of-concerns as the Cloud Run path:

```bash
PROJECT_ID="<PROJECT_ID>"
REGION="<REGION>"
AR_REPO="<AR_REPO>"
SA_NAME="<APP_NAME>-deployer"          # used by GitHub Actions
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
VM_SA_NAME="<APP_NAME>-vm"             # attached to the running VM
VM_SA_EMAIL="${VM_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud services enable compute.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iamcredentials.googleapis.com

gcloud artifacts repositories create "${AR_REPO}" \
  --repository-format=docker --location="${REGION}"

# VM runtime SA: reads secrets, pulls images
gcloud iam service-accounts create "${VM_SA_NAME}"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${VM_SA_EMAIL}" --role="roles/secretmanager.secretAccessor"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${VM_SA_EMAIL}" --role="roles/artifactregistry.reader"

# Deployer SA: builds/pushes images, SSHes into the VM via IAP
gcloud iam service-accounts create "${SA_NAME}"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/compute.osAdminLogin"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/iap.tunnelResourceAccessor"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/compute.viewer"
# deployer SA needs to SSH in AS the VM's own SA identity
gcloud iam service-accounts add-iam-policy-binding "${VM_SA_EMAIL}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/iam.serviceAccountUser"
```

If using a service-account key instead of WIF (see `sa-key-setup.md`), this is also where you'd generate and download the deployer SA's key — never commit it, paste it straight into a GitHub secret and delete the local file.

### 2. `create-vm.sh` — the VM itself, Container-Optimized OS

COS is the point here: it's a minimal, auto-patching image that ships with Docker and `docker-credential-gcr` preinstalled, so there's no OS-level package management to maintain.

```bash
gcloud compute firewall-rules create <APP_NAME>-allow-http \
  --direction=INGRESS --action=ALLOW --rules=tcp:80 \
  --source-ranges=0.0.0.0/0 --target-tags=<APP_NAME>

gcloud compute instances create "<VM_NAME>" \
  --zone="<ZONE>" \
  --machine-type="<MACHINE_TYPE>" \
  --image-family=cos-stable \
  --image-project=cos-cloud \
  --boot-disk-size="<DISK_SIZE>" \
  --boot-disk-type=pd-balanced \
  --service-account="<VM_SA_EMAIL>" \
  --scopes=cloud-platform \
  --tags=<APP_NAME> \
  --metadata=enable-oslogin=TRUE \
  --metadata-from-file=startup-script=vm-startup.sh
```

`enable-oslogin=TRUE` is what lets the deployer SA's IAM roles (above) actually control SSH access, instead of managing SSH keys by hand.

### 3. `vm-startup.sh` — runs on every VM boot, pulls secrets into a local `.env`

This runs as root on first boot (and every reboot). Its job is just to make secrets available to containers that get started later by the deploy workflow — it does *not* start the app containers itself.

```bash
#!/usr/bin/env bash
set -eu
PROJECT_ID="<PROJECT_ID>"
APP_DIR="/var/lib/<APP_NAME>"   # COS's /opt is read-only; use /var/lib for writable state
DATA_DIR="${APP_DIR}/data"
ENV_FILE="${APP_DIR}/.env"

mkdir -p "${APP_DIR}" "${DATA_DIR}"
export HOME="${APP_DIR}"        # COS's /root is read-only too
docker-credential-gcr configure-docker --registries="<REGION>-docker.pkg.dev" || true

ACCESS_TOKEN=$(curl -sSf -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

SECRET_VALUE=$(curl -sSf -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/<SECRET_NAME>/versions/latest:access" \
  | python3 -c "import sys, json, base64; print(base64.b64decode(json.load(sys.stdin)['payload']['data']).decode())")

cat > "${ENV_FILE}" <<EOF
<ENV_VAR_NAME>=${SECRET_VALUE}
EOF
chmod 600 "${ENV_FILE}"
```

The pattern of hitting the VM metadata server directly for an access token (rather than `gcloud auth`) is deliberate — COS doesn't have the `gcloud` CLI installed, only Docker and curl.

## The deploy workflow: build, then SSH in and `docker run`

Unlike Cloud Run, there's no managed "deploy" API call — the workflow builds images, pushes them, then SSHes into the VM (through Identity-Aware Proxy, so no public SSH port needs to be open) and runs `docker pull` + `docker run` by hand.

```yaml
jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}   # or credentials_json: for SA-key path
          service_account: ${{ secrets.GCP_DEPLOYER_SA }}
      - uses: google-github-actions/setup-gcloud@v2
      - run: gcloud auth configure-docker <REGION>-docker.pkg.dev --quiet

      - run: |
          docker build -t <IMAGE>:${GITHUB_SHA::7} -t <IMAGE>:latest ./<SUBPROJECT_DIR>
          docker push <IMAGE>:${GITHUB_SHA::7}
          docker push <IMAGE>:latest

      # gcloud compute ssh generates a fresh OS Login key on every run and
      # registers it to the deployer SA's profile. Left unpruned, the profile
      # hits a 32 KiB size cap and every subsequent SSH starts failing with
      # FAILED_PRECONDITION — this bites you weeks after setup, not on day one.
      - run: |
          for fp in $(gcloud compute os-login ssh-keys list --format="value(value.fingerprint)"); do
            gcloud compute os-login ssh-keys remove --key "$fp" --quiet || true
          done

      - run: |
          gcloud compute ssh --zone="<ZONE>" --tunnel-through-iap "<VM_NAME>" --command="
            set -eu
            sudo docker pull <IMAGE>:${GITHUB_SHA::7}
            sudo docker rm -f <CONTAINER_NAME> 2>/dev/null || true
            sudo docker run -d --name <CONTAINER_NAME> --restart always \
              --env-file /var/lib/<APP_NAME>/.env \
              -p 80:<CONTAINER_PORT> \
              <IMAGE>:${GITHUB_SHA::7}
            sudo docker image prune -f || true
          "
```

### Gotchas specific to this path, all encountered in a real deployment

- **COS's `/root` is read-only.** Anything that writes to `$HOME` (like `docker-credential-gcr` writing `~/.docker/config.json`) needs `HOME` redirected to a writable path first, both in the startup script and in the SSH command if `sudo` is involved (root's `$HOME` under `sudo` is still `/root` unless you export `HOME` explicitly and pass `DOCKER_CONFIG` through to the `sudo docker` calls).
- **The OS Login key accumulation issue above.** This is silent until it isn't — budget for the prune step in every deploy, not just as a one-off fix when it breaks.
- **Small VMs run out of disk from accumulated images.** `docker system prune -af` before pulling the new image, if the machine type is small (e.g. `e2-small`) and deploys happen often enough for old layers to pile up.
- **No Docker Compose on COS by design** — it's not preinstalled and adding it defeats the point of using a minimal, auto-patching base image. Multi-container setups on a VM are wired with plain `docker run` + `docker network create`, as shown in the two-container nginx+backend case this pattern is drawn from.
- **First deploy has to wait for the startup script.** If the deploy workflow SSHes in before the VM's first-boot startup script has finished writing `.env`, the container will start with missing config. A short retry/wait loop checking for the `.env` file's existence before proceeding is cheap insurance.
- **The quote escaping inside `--command="..."` is genuinely fragile — verify by running it, not by reading it.** The whole remote script is one double-quoted string from bash's perspective, so every `"` that needs to survive to the remote shell has to be escaped (`\"`), and every `$` that should NOT be expanded locally before SSH even sends the command needs escaping too (`\$`). It's easy to get this half-right in a way that parses but silently drops a variable or a quote on the remote side. If you change anything inside the `--command=` block, actually trigger the workflow (or run the `gcloud compute ssh` command by hand first) rather than trusting that it reads correctly — a real deployment that hit this exact class of bug left an inline comment in its script specifically warning the next editor about it, which is the right instinct.
