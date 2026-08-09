# Cloud Run deploy — annotated

Two real shapes, both WIF-authenticated: a **single-service** deploy (one image, one Cloud Run service) and a **multi-service** deploy (e.g. backend + frontend, each its own service, wired together at deploy time).

## Single-service shape

This is the common case: one Dockerfile, one Cloud Run service. Full workflow template at `../assets/cloud-run-workflow.yml`.

```yaml
env:
  PROJECT_ID: <PROJECT_ID>
  REGION: <REGION>                    # e.g. asia-northeast1
  AR_HOST: <REGION>-docker.pkg.dev
  AR_REPO: <ARTIFACT_REGISTRY_REPO>   # an existing or new Artifact Registry Docker repo
  SERVICE: <SERVICE_NAME>
  IMAGE_NAME: <SERVICE_NAME>

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write               # required for WIF — without this the auth step fails
    outputs:
      image: ${{ steps.meta.outputs.image }}
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3

      - id: gcp-auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_DEPLOYER_SA }}
          token_format: access_token   # needed so the next step can use the access token directly

      - uses: docker/login-action@v3
        with:
          registry: ${{ env.AR_HOST }}
          username: oauth2accesstoken
          password: ${{ steps.gcp-auth.outputs.access_token }}

      - id: meta
        run: |
          SHORT_SHA=$(echo "${{ github.sha }}" | cut -c1-7)
          echo "image=${{ env.AR_HOST }}/${{ env.PROJECT_ID }}/${{ env.AR_REPO }}/${{ env.IMAGE_NAME }}:${SHORT_SHA}" >> "$GITHUB_OUTPUT"

      - uses: docker/build-push-action@v6
        with:
          context: ./<SUBPROJECT_DIR>   # e.g. ./anaplan-skill in a monorepo, or . at repo root
          push: true
          tags: |
            ${{ steps.meta.outputs.image }}
            ${{ env.AR_HOST }}/${{ env.PROJECT_ID }}/${{ env.AR_REPO }}/${{ env.IMAGE_NAME }}:latest
          cache-from: type=gha,scope=${{ env.SERVICE }}
          cache-to: type=gha,mode=max,scope=${{ env.SERVICE }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_DEPLOYER_SA }}
          # no token_format here — deploy-cloudrun manages its own gcloud auth session

      - id: deploy
        uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: ${{ env.SERVICE }}
          region: ${{ env.REGION }}
          image: ${{ needs.build.outputs.image }}
          secrets: |
            <ENV_VAR_NAME>=<SECRET_NAME>:latest
            # one line per secret — see secret-manager-setup.md for creating these
          flags: >-
            --allow-unauthenticated
            --service-account=<RUNTIME_SA_EMAIL>
            --memory=2Gi
            --cpu=1
            --timeout=3600
            --max-instances=2
            --min-instances=0
            --port=8080

      - run: echo "Service URL: ${{ steps.deploy.outputs.url }}" >> "$GITHUB_STEP_SUMMARY"
```

### Notes on the flags that actually matter

- `--allow-unauthenticated` opens the Cloud Run IAM gate. This is correct when the app has its **own** login/auth layer (app-level auth is the real security boundary, e.g. a Streamlit login screen) — it is wrong for an internal-only service that should require Google SSO or IAM-based access. Decide this deliberately, don't default to it.
- `--service-account=<RUNTIME_SA_EMAIL>` is a *separate* service account from the one GitHub Actions uses to deploy. See `secret-manager-setup.md` for why the deployer SA needs an extra IAM grant to even be allowed to set this flag.
- `--timeout` matters for anything that can run a single request longer than the 5-minute Cloud Run default (e.g. a Streamlit app doing a long data fetch on first load).
- `--min-instances=0` is what gives you scale-to-zero (and the associated cold start). Set it above 0 only if cold starts are a measured problem, not a hypothetical one.
- Tag with **both** the short SHA and `latest`. `latest` is what most `deploy-cloudrun` calls reference for convenience, but the SHA tag is what you'd roll back to if `latest` turns out bad — always push both.

## Multi-service shape (e.g. backend + frontend)

When the app is naturally two (or more) independent HTTP services rather than one, deploy each as its own Cloud Run service instead of reaching for a VM. The key trick: build both images in a matrix, then deploy the backend first and pass its resulting URL into the frontend's deploy step as an env var.

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    strategy:
      matrix:
        include:
          - name: backend
            context: ./backend
          - name: frontend
            context: ./frontend
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - id: gcp-auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_DEPLOYER_SA }}
          token_format: access_token
      - uses: docker/login-action@v3
        with:
          registry: <REGION>-docker.pkg.dev
          username: oauth2accesstoken
          password: ${{ steps.gcp-auth.outputs.access_token }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: <REGION>-docker.pkg.dev/${{ secrets.GCP_PROJECT_ID }}/<AR_REPO>/<APP_NAME>-${{ matrix.name }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha,format=long
      - uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha,scope=${{ matrix.name }}
          cache-to: type=gha,mode=max,scope=${{ matrix.name }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_DEPLOYER_SA }}

      - id: deploy-backend
        uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: <APP_NAME>-backend
          region: <REGION>
          image: <REGION>-docker.pkg.dev/${{ secrets.GCP_PROJECT_ID }}/<AR_REPO>/<APP_NAME>-backend:sha-${{ github.sha }}
          flags: >-
            --allow-unauthenticated
            --service-account=<RUNTIME_SA_EMAIL>
            --memory=512Mi
            --cpu=1
            --max-instances=3

      - id: deploy-frontend
        uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: <APP_NAME>-frontend
          region: <REGION>
          image: <REGION>-docker.pkg.dev/${{ secrets.GCP_PROJECT_ID }}/<AR_REPO>/<APP_NAME>-frontend:sha-${{ github.sha }}
          env_vars: |
            BACKEND_URL=${{ steps.deploy-backend.outputs.url }}
          flags: >-
            --allow-unauthenticated
            --service-account=<RUNTIME_SA_EMAIL>
            --memory=256Mi
            --cpu=1
            --max-instances=3
```

The frontend build step (if it's a static SPA) may also need the backend's URL as a **build-time** arg rather than a runtime env var, depending on whether the frontend framework bakes API URLs in at build time or reads them at runtime — check which your framework does before assuming `env_vars:` alone is enough.
