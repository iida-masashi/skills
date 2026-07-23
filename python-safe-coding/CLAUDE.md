# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Scope: the **python-safe-coding** skill. The repo-wide `CLAUDE.md` files at
> `gemini/` and `gemini/.gemini/skills/` still apply; this file adds only what
> is specific to this skill. The skill ships a unified `psc` CLI (Ruff + MyPy +
> a Polars-First AST policy + pytest coverage floor) and **must pass its own
> gate** — every change here is validated by the same `psc gate` it ships.

## Commands

```bash
uv sync
uv pip install -e .          # exposes the `psc` console script
uv pip install -e '.[heal]'  # add the optional Gemini self-healer

psc gate --target . --baseline .psc-baseline.json   # full gate (use before committing)
psc gate --since main                               # diff-aware: Ruff/AST on changed files only

# Run the suite directly:
uv run pytest tests/
uv run pytest tests/test_gate.py::test_name          # single test
uv run pytest tests/ --cov=src --cov-fail-under=80    # coverage floor is 80%

uv run ruff check src tests
uv run mypy src --ignore-missing-imports             # strict mode (see pyproject)
```

`psc prepush` runs compile-check + `uv lock --check` + project conflict rules.
On Windows PowerShell, set UTF-8 first (`[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`).

## Architecture

`src/python_safe_coding/` is a flat module set wired together by `cli.py`. The
key non-obvious design choices:

- **`cli.py`** — the only entry point (`psc` console script). Each subcommand is
  a `_cmd_*` function dispatched via argparse `set_defaults(func=...)`. Read the
  module docstring for the subcommand map.

- **Ruff-first policy** — the custom checker enforces *only* what Ruff cannot
  express. Today that is a single rule: **Polars First** (`import pandas` is
  banned outright, even when used — Ruff's `PD` category warns about usage, not
  the import). Naive datetime → Ruff `DTZ005`, bare except → `BLE001`, mutable
  defaults → `B006`. **Before adding a custom AST rule, confirm no Ruff rule
  covers it** — see `docs/adr/0001-ruff-first-policy.md`. Each custom rule is debt.

- **`ast_checker.py`** — the Polars-First checker. Walks files in parallel via
  `ThreadPoolExecutor` past `_PARALLEL_THRESHOLD` (16 files); `ast.parse`
  releases the GIL so threads scale without ProcessPool spawn cost. Output is
  **sorted by path** so parallel scans produce stable diffs. ⚠️ When you add or
  change a rule, bump `_CHECKER_VERSION` — otherwise the per-file cache silently
  reuses pre-change "clean" verdicts.

- **`cache.py`** — opt-in per-file cache keyed by `(abs_path, mtime_ns, size,
  checker_version)`. Off unless `--cache-dir` is passed. The cache dir is opaque
  JSON; consumers must `.gitignore` it.

- **`baseline.py`** — `psc baseline generate` snapshots current AST violations
  by fingerprint so legacy repos adopt incrementally; only *new* violations fail
  the gate. Stale entries (already-fixed) are flagged, not failed, so the
  baseline shrinks over time. MyPy/Ruff are **not** baselined — only the AST policy.

- **`editor.py`** (`psc replace`) — AST-based code replacement, never regex. It
  replaces by `Class.method` dotted lookup and **includes decorators in the
  replaced span** to avoid orphan decorator lines.

- **`healer.py`** (`psc heal`) — optional Gemini repair loop. Imported lazily in
  `cli.py` so the base install never pulls the Vertex AI SDK; it's excluded from
  coverage (`[tool.coverage.run] omit`). Only touch when working on `[heal]`.

### Diff-aware vs full-tree

`--since <ref>` limits **Ruff and the AST checker** to changed `.py` files (via
`git diff --diff-filter=AMR <since>...HEAD`). **MyPy always runs full-tree** —
per-file mypy breaks cross-module type inference. Git failure falls back to a
full scan with a warning, never a silent skip.

### Exit codes are a contract

`0` pass · `1` policy/test violation (red CI, dev fixes code) · `2` internal
error (gate bug) · `3` config error (missing toml/extras, malformed baseline).
CI alert routing branches on these — do not collapse or repurpose them. New
codes would start at `4+`. See `docs/reference/exit-codes.md`.

## Conventions specific to this skill

- **Argv lists, never `shell=True`.** Every subprocess takes a list so
  user-supplied targets can't become shell metacharacters. `gate.py` and the CLI
  carry targeted `S603/S607` per-file ignores in `pyproject.toml` for exactly
  this reason — extend those ignores narrowly, don't disable the rule globally.
- **`# nosec` requires a comment** explaining why, plus an issue-tracker link.
- **No stray `print()`** outside CLI entry points — structured `logging` only.
  ASCII status tags (`[OK]`, `[FAIL]`, `[ERROR]`); emoji breaks cp932 terminals.
- Consumer-repo conflict rules live under `[tool.python_safe_coding]
  conflict_rules` and a rule fires only when **all** its packages are declared
  together; `psc prepush` evaluates them.

## ADRs

`docs/adr/` records *why* decisions were made — read the relevant one before
reversing a design choice (Ruff-first, AST-only baseline, healer-as-extra,
thread-pool + mtime cache).
