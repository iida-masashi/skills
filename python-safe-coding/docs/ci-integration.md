# CI Integration

`psc` is designed to be the single command your CI invokes. Three integration
patterns, in increasing levels of "shift-left":

## 1. GitHub Actions

Copy [`.github/workflows/quality-gate.yml`](../.github/workflows/quality-gate.yml)
into the consumer repository. It:

- Pulls full git history (`fetch-depth: 0`) so `psc gate --since` can compute
  diffs against the PR base.
- Uses `astral-sh/setup-uv@v3` and `uv sync --frozen` for deterministic installs.
- On PRs, runs `psc gate --since origin/<base_ref>` (diff-aware: only changed
  files trigger Ruff and the AST policy).
- On pushes to `main`, also runs `psc prepush` (uv lock sync + conflict rules).

### Status reporting

`--github-summary` produces a markdown report appended to
`$GITHUB_STEP_SUMMARY`, visible in the Actions UI.

### Exit-code contract

| Code | Meaning |
|------|---------|
| 0    | Pass |
| 1    | Policy / test violation (red CI) |
| 2    | Internal error (red CI; investigate) |
| 3    | Configuration error (red CI; the workflow setup is wrong) |

## 2. pre-commit

For commit-time enforcement, install
[pre-commit](https://pre-commit.com) and copy
[`templates/.pre-commit-config.example.yaml`](../templates/.pre-commit-config.example.yaml)
to the consumer repo as `.pre-commit-config.yaml`.

```bash
pre-commit install                       # install commit-time hooks
pre-commit install --hook-type pre-push  # install pre-push hooks
```

Hooks bundled with this skill:

- **`psc-ast`** — runs on every commit, pre-commit passes the changed files.
  The `--baseline .psc-baseline.json` arg suppresses already-known violations
  so existing repos can adopt incrementally.
- **`psc-prepush`** — runs once before each push.

## 3. Local Make target

For repos that prefer `make` over pre-commit:

```makefile
.PHONY: gate
gate:
	uv run psc gate --target . --baseline .psc-baseline.json
```

## Adopting on a legacy codebase

The first run of `psc ast` on a real codebase usually finds many violations.
Two-step adoption:

```bash
# 1. Capture today's state as the baseline.
uv run psc baseline generate src --output .psc-baseline.json
git add .psc-baseline.json && git commit -m "chore: snapshot psc baseline"

# 2. From this point on, only NEW violations fail the gate.
uv run psc ast --baseline .psc-baseline.json src
```

When a developer fixes a violation, regenerate to keep the baseline tight:

```bash
uv run psc baseline regenerate src --output .psc-baseline.json
```

`psc gate` and `psc ast` both warn when stale entries (already-fixed
violations still listed in the baseline) accumulate.

## Verifying the workflow

GitHub Actions YAML often has subtle breakage (action renames, flag changes).
Always verify by triggering the workflow on a throwaway branch *before*
relying on it as a merge gate.
