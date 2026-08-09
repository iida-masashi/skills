---
name: gcp-docker-deploy
description: Deploy any Dockerized app (Streamlit, FastAPI, Node.js, React+nginx, etc.) to Google Cloud via GitHub Actions — Cloud Run or a Compute Engine VM, with Workload Identity Federation (preferred) or a service-account JSON key. Use this whenever the user wants to "deploy to Cloud Run", "deploy to GCP", "GCPにデプロイ", "set up GitHub Actions to build a Docker image and push to GCP", asks how to get a container running on Google Cloud, wants CI/CD for a containerized app, or is debugging a broken/silent GCP deploy workflow (e.g. a workflow that never triggers, ModuleNotFoundError inside a container that works locally, or an IAM/auth failure in Actions). Also use it when the user is choosing between Cloud Run and a VM for a new deployment, or wants to compare Workload Identity Federation against a service-account key.
---

# GCP Docker Deploy

This skill packages a working pattern for shipping a Dockerized app to Google Cloud through GitHub Actions. It exists because the individual pieces (WIF trust setup, monorepo path scoping, `PYTHONPATH` inside a container, Cloud Run vs. VM deploy steps) each have a specific, easy-to-get-wrong shape — and getting one piece wrong tends to fail silently (a workflow that never runs, a container that crashes on the first import) rather than with a clear error.

Two real, working deployments back this skill:
- A **Cloud Run** deployment of a Streamlit app, using **WIF**, deployed from a subdirectory of a monorepo.
- A **Compute Engine VM** deployment of a FastAPI + React app, using a **service-account JSON key**, deployed via SSH-over-IAP into a Container-Optimized OS instance.

Both patterns are documented in `references/` with the actual working YAML/shell, generalized with placeholders.

## Step 1 — Decide: Cloud Run or a VM?

Default to **Cloud Run** unless something concrete rules it out. Cloud Run is less to operate — no SSH, no OS patching, no manual container lifecycle — and "looks stateful" is not actually disqualifying: a Streamlit app that keeps a session alive for minutes is still just serving HTTP requests, which is exactly what Cloud Run is for.

Reach for a **VM** only when one of these is genuinely true:
- The workload needs a **GPU** or other special hardware Cloud Run doesn't expose.
- It needs **persistent local disk** that must survive independently of container restarts and isn't backed by a mounted volume service (Cloud Run containers are ephemeral; a VM's disk isn't).
- It speaks a **non-HTTP protocol**, or a single logical service needs **multiple ports** open simultaneously (Cloud Run exposes exactly one per service).
- It must run **continuously regardless of traffic** in a way that makes scale-to-zero actively wrong (not just "I'd rather not have cold starts").
- Its containers are wired together with **direct container-to-container networking that isn't naturally split into independent request-response services** — e.g. an nginx container reverse-proxying to a backend container over a private Docker network behind one exposed port (the openSCM case). The pairing itself doesn't map to Cloud Run's one-image-per-service model without extra plumbing.

**Multiple containers alone don't force a VM.** A frontend and a backend are routinely two separate Cloud Run *services* that each get their own URL, with the frontend's env var pointed at the backend's deployed URL (see `references/cloud-run-deploy.md`'s multi-service variant, based on a real two-service Cloud Run deployment). Reach for a VM only when the containers need to stay on the *same* private network behind a *single* public entrypoint, not just when there's more than one image.

If none of those apply, it's Cloud Run — see `references/cloud-run-deploy.md`.
If one does, see `references/vm-deploy.md`.

You can mix approaches within one project: nothing stops a monorepo from deploying one subproject to Cloud Run and another to a VM, each with its own workflow file (see Step 2).

## Step 2 — Check the repo structure first

GitHub only ever looks for workflows in `<repo-root>/.github/workflows/`. A workflow file placed inside a subproject — `some-subproject/.github/workflows/deploy.yml` in a monorepo — is invisible to GitHub. It sits in git history looking correct, never triggers, and never errors. There's no warning; it's just dead.

Before writing any workflow YAML, confirm:
1. Where the actual `.git` root is (`git rev-parse --show-toplevel`).
2. That the new workflow file goes under `<git-root>/.github/workflows/`, even if the app itself lives in `some-subproject/`.
3. If this is a monorepo with multiple deployable subprojects, that `on.push.paths` scopes the trigger to that subproject's own path plus the workflow file itself — otherwise an unrelated change anywhere in the repo redeploys everything.

```yaml
on:
  push:
    branches: [main]
    paths:
      - '<subproject-dir>/**'
      - '.github/workflows/<this-workflow-file>.yml'
```

## Step 3 — Choose the authentication path

**Prefer Workload Identity Federation (WIF).** No long-lived key ever exists — GitHub Actions exchanges its own OIDC token for short-lived GCP credentials at run time. Nothing to rotate, nothing to leak in a leaked secret dump. Full setup in `references/wif-setup.md`.

**Use a service-account JSON key only when WIF setup isn't practical** (e.g. a fast prototype, a project where IAM changes require approval you don't have time for). The key gets pasted into a GitHub secret and used directly by `google-github-actions/auth@v2`+ with `credentials_json:`. This is real, working, and simpler to stand up — the tradeoff is a long-lived credential sitting in GitHub's secret store that has to be rotated manually and is a bigger blast radius if GitHub secrets are ever compromised. Setup in `references/sa-key-setup.md`.

Both paths end at the same place: a `google-github-actions/auth@v2` step early in each job that needs GCP access.

## Step 4 — Fix the Dockerfile for your app's actual packaging

This is the single most common silent-failure point: **the container builds fine and then crashes on startup** with an import error that never happened locally.

The specific case to check for: if the app is a Python project managed by `uv` and it's *not* a properly packaged distribution — check `uv.lock` for `source = { virtual = "." }`, or the absence of a `[build-system]` table in `pyproject.toml` — then `uv sync` inside the container installs only the dependencies, not the app's own source tree into site-packages. Locally this is invisible because `uv run` adds the repo root to `sys.path` automatically. Inside Docker, nothing does that for you unless you tell it to:

```dockerfile
WORKDIR /app
ENV PYTHONPATH=/app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY <app-source-dir>/ ./<app-source-dir>/
```

If a local run script (`run_local.ps1`, a Makefile target, etc.) exists for this app *outside* Docker, check it sets the same `PYTHONPATH` — it's exactly as easy to miss there, and if it's missing there too, local runs of the container-bound entrypoint will fail with the identical error before you ever get to CI.

This isn't Python-specific in spirit — any language/framework where "run from repo root" and "run from inside a built artifact" resolve imports/modules differently deserves the same check. Node with path aliases in `tsconfig.json` that aren't compiled away, Go with a `replace` directive in `go.mod` pointing at a local path, etc. The pattern is: **something about local dev quietly does path resolution that the container image needs done explicitly.**

## Step 5 — Write the workflow

Use `assets/cloud-run-workflow.yml` or `assets/vm-workflow.yml` as a starting template (copy, don't reference — GitHub Actions needs the file to actually live in the repo). Both follow the same build → deploy two-job shape:

- **build**: auth to GCP → log in to Artifact Registry → `docker/build-push-action@v6` tagged with both the short commit SHA and `latest` (SHA tag gives you a rollback target; `latest` is a convenience pointer, not a substitute for the SHA tag)
- **deploy** (`needs: build`): auth to GCP again (each job gets fresh, short-lived credentials — this is a feature of WIF, not wasted work) → the platform-specific deploy step

See `references/cloud-run-deploy.md` or `references/vm-deploy.md` for the full annotated version, including how secrets get wired in (Step 6) and the resource-sizing flags that matter (memory/cpu/timeout/instance counts for Cloud Run; machine type/disk/firewall for a VM).

## Step 6 — Wire up Secret Manager

Runtime config (API keys, DB passwords, app-level login credentials) goes in Secret Manager, never baked into the image or committed anywhere. Two service accounts are involved, and mixing up which one needs which role is the most common misconfiguration here:

- **Deployer SA** (used by GitHub Actions): needs `roles/artifactregistry.writer` + `roles/run.admin` (or the VM/compute equivalents), *and* `roles/iam.serviceAccountUser` on the **runtime SA** specifically — without that last grant, `deploy-cloudrun`'s `--service-account=<runtime-sa>` flag fails with a permission error that looks like it's about Cloud Run but is actually about impersonation rights.
- **Runtime SA** (attached to the running container/VM): needs `roles/secretmanager.secretAccessor`, scoped to just the secrets it actually reads if you want least-privilege, or project-wide if that's overkill for the situation.

Full `gcloud` commands in `references/secret-manager-setup.md`.

## Step 7 — Verify before you push, and after you deploy

**Before pushing**, catch the Step 4 class of bug locally:
```bash
docker build -t local-test ./<subproject-dir>
docker run --rm -p 8080:8080 --env-file <dummy-env-file> local-test
curl http://localhost:8080/<health-path>
```
If this fails, CI will fail the same way, just slower and more expensively.

**After a push**, confirm the deploy actually happened, not just that the workflow ran:
```bash
gh run list --repo <owner>/<repo> --workflow=<workflow-file>.yml --limit 3
gcloud run services describe <service> --region=<region> --format='value(status.url,status.latestReadyRevisionName)'
```
A green workflow run is necessary but not sufficient — check the Cloud Run revision is actually `Ready`, and hit the app's health endpoint once to confirm the container didn't crash-loop after a successful deploy step (Cloud Run can report a deploy as "successful" for a revision that then fails its own startup probe).

## Reference files

- `references/wif-setup.md` — full WIF pool/provider/service-account setup, idempotent gcloud commands
- `references/sa-key-setup.md` — service-account JSON key alternative, with the rotation/exposure tradeoff spelled out
- `references/cloud-run-deploy.md` — annotated two-job Cloud Run workflow, secrets wiring, resource flags
- `references/vm-deploy.md` — VM creation, Container-Optimized OS startup script, SSH-over-IAP deploy step, OS Login key accumulation gotcha
- `references/secret-manager-setup.md` — secret creation and the two-service-account IAM binding pattern
- `assets/cloud-run-workflow.yml` — copy-paste starting point for a Cloud Run deploy workflow
- `assets/vm-workflow.yml` — copy-paste starting point for a VM deploy workflow
- `assets/dockerfile-python-uv.md` — Dockerfile template for an unpackaged uv Python project
