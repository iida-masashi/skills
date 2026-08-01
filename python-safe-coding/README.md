# Python Safe Coding Skill

**"The Guardian of Quality"** — a unified `psc` CLI bundling Ruff (lint/
security/complexity), MyPy (strict), a Polars-First AST policy, and
pytest with coverage enforcement. Optional Gemini self-healer.

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | Philosophy and charter |
| [docs/reference/cli.md](docs/reference/cli.md) | Every subcommand and flag |
| [docs/reference/rules.md](docs/reference/rules.md) | Where each rule lives (Ruff vs custom) |
| [docs/reference/exit-codes.md](docs/reference/exit-codes.md) | Exit-code contract |
| [docs/ci-integration.md](docs/ci-integration.md) | GitHub Actions + pre-commit recipes |
| [docs/adr/](docs/adr/) | Architecture decision records |
| [BACKLOG.md](BACKLOG.md) / [ROADMAP.md](ROADMAP.md) | Status and what's next |

## Quick Start

```bash
uv sync
uv pip install -e .          # exposes the `psc` console script
uv pip install -e '.[heal]'  # add Gemini self-healer support
```

## Commands

```bash
psc gate     [--target .] [--since main] [--baseline FILE]
             [--coverage-threshold 80] [--github-summary]

psc ast      [TARGET ...]   [--since main] [--baseline FILE]
                            [--cache-dir .psc-cache]

psc baseline {generate,regenerate,diff} [TARGET ...]
                            [--output .psc-baseline.json]
                            [--cache-dir .psc-cache]

psc replace  --file F --target NAME --new-code FILE

psc heal     [--log STR | --file LOG | -]
             [--auto-commit | --dry-run | --patch-only PATH]

psc prepush  [--target .]
```

## Highlights

- **Diff-aware** — `psc gate --since main` runs Ruff and the AST policy
  only on `.py` files changed against the ref. MyPy stays full-tree.
- **Baselines** — `psc baseline generate` snapshots known violations so
  legacy repos can adopt without fixing everything up front. Stale entries
  are flagged so the baseline shrinks over time.
- **Parallel + cached AST scans** — `--cache-dir` opts in to a per-file
  cache keyed by `(path, mtime_ns, size, _CHECKER_VERSION)`. Bumping the
  checker version invalidates everything automatically.
- **Healer is optional** — install `[heal]` extras only when you want the
  Gemini-driven repair loop. Base install does not pull the Google Gen AI SDK.
- **Exit codes are a contract** — `0/1/2/3` for pass/violation/internal/
  config; CI alert routing can branch on them.

## Project conflict rules

```toml
# pyproject.toml of the consumer repo
[tool.python_safe_coding]
conflict_rules = [
    { packages = ["darts", "neuralprophet"], reason = "Lightning version clash" },
]
```

`psc prepush` evaluates these on every run.

## Running the gate locally

```bash
psc gate --target . --baseline .psc-baseline.json
```

Output:
```
[OK] Code Quality (Ruff) Passed
[OK] Type Checker (MyPy) Passed
[OK] Unit Tests (Pytest) Passed
[OK] Quality gate passed.
```
