# Dockerfile template — unpackaged uv Python project

For a Python app managed by `uv` where the project is a "virtual" workspace
(`uv.lock` has `source = { virtual = "." }`, no `[build-system]` in
`pyproject.toml`) rather than a proper installable package. This is common
for apps under a monorepo subdirectory that were never set up to be pip-
installable — locally, `uv run` papers over this by adding the repo root to
`sys.path` automatically; inside Docker, nothing does that unless told to.

```dockerfile
# syntax=docker/dockerfile:1.6
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Copy lockfiles first for layer caching — dependency installs only
# invalidate when pyproject.toml/uv.lock change, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Now copy the actual source tree. --no-install-project above means this
# step's content isn't installed into site-packages either — PYTHONPATH=/app
# is what makes `from <app_package>.module import ...` resolve at runtime,
# the same way `uv run` does it for free from the repo root locally.
COPY <APP_SOURCE_DIR>/ ./<APP_SOURCE_DIR>/

EXPOSE <CONTAINER_PORT>

# Cloud Run injects $PORT; default it for local `docker run` testing.
CMD ["sh", "-c", "uv run <YOUR_START_COMMAND> --port=${PORT:-<CONTAINER_PORT>}"]
```

## Corresponding `.dockerignore`

Keep the build context small and avoid leaking local-only files into the image:

```
.git
.github
.venv
.env
tests/
__pycache__/
*.pyc
.pytest_cache
*.xlsx
*.csv
```

**Do not** ignore `uv.lock` — `uv sync --frozen` needs it and will fail without it.

## The same trap outside Docker

If a local run script (PowerShell script, Makefile target, shell wrapper)
exists for launching this app *without* going through `uv run <path>`
directly, check it also sets `PYTHONPATH` to the repo root. It's exactly as
easy to omit there, and if it's missing, local runs will fail with the
identical `ModuleNotFoundError` before you even get to testing the container.

```powershell
# PowerShell example
$env:PYTHONPATH = $PSScriptRoot
uv run <your start command>
```

## Non-Python analogues

The underlying issue — "local dev quietly resolves imports/modules in a way
the built artifact doesn't replicate" — shows up in other ecosystems too:

- **Node.js** with TypeScript path aliases (`compilerOptions.paths` in
  `tsconfig.json`) that work under `ts-node`/dev server but aren't rewritten
  by a plain `tsc` build — needs a path-rewriting step (e.g.
  `tsc-alias`) baked into the Docker build.
- **Go** with a `replace` directive in `go.mod` pointing at a local
  filesystem path — works when building from the monorepo checkout, breaks
  if the Docker build context doesn't include that sibling path.

The fix is the same shape every time: identify what local dev does
implicitly, and do it explicitly in the Dockerfile.
