---
name: python-safe-coding
description: Guardian of Quality. AST-based safe refactoring, strict typing enforcement, and a unified `psc` quality gate.
---

# Python Safe Coding Skill

A unified quality gate (`psc`) bundling Ruff, MyPy, a Polars-First AST policy,
and pytest with coverage enforcement. Optional Gemini self-healer.

This document is the **philosophy / charter**. For usage details, see:

- [`docs/reference/cli.md`](docs/reference/cli.md) — every subcommand and flag.
- [`docs/reference/rules.md`](docs/reference/rules.md) — policy rules and where they live (Ruff vs custom).
- [`docs/reference/exit-codes.md`](docs/reference/exit-codes.md) — exit-code contract.
- [`docs/ci-integration.md`](docs/ci-integration.md) — GitHub Actions + pre-commit recipes.
- [`docs/adr/`](docs/adr/) — architecture decision records explaining *why*.
- [`README.md`](README.md) — quick-start.

## Philosophy

### 1. Trust Ruff first
Naive `datetime.now()` is delegated to Ruff `DTZ005`; bare `except:` to
`BLE001`; mutable defaults to `B006`. The custom AST checker only covers what
Ruff cannot express today (currently: Polars First — banning `import pandas`).
Every custom rule we add is debt; Ruff rules are leverage.
See [ADR 0001](docs/adr/0001-ruff-first-policy.md) for the rationale.

### 2. Argv lists, never `shell=True`
User-supplied targets cannot be reinterpreted as shell metacharacters. Every
subprocess in this skill takes a list. If you find yourself wanting `shell=True`,
shell out to a script you wrote, not a string the user wrote.

### 3. AST over regex for code rewriting
`psc replace` includes decorators in the replaced span to avoid orphan lines,
and uses `Class.method` dotted lookup for nested targets. Regex-based code
rewriting is a footgun.

### 4. TDD
Write tests before code. Coverage floor is 80%. Tests live in `tests/` next to
`src/`; they are not optional.

### 5. Polars First
`import pandas` is forbidden. Use Polars LazyFrames. The Rust core is faster,
the API is more honest about what's lazy vs eager, and the type signatures
are not lies.

### 6. Reproducibility
Lock with `uv lock` and verify on push (`psc prepush`). No `pip freeze`
artifacts. The lock file is part of the contract.

### 7. Security First
Bandit categories (`S`) ship in the Ruff config and run by default. No
`# nosec` without a comment explaining why and a link to the issue tracker.

### 8. Observability
Structured `logging` only — no stray `print()` outside CLI entry points. ASCII
status tags (`[OK]`, `[FAIL]`, `[ERROR]`) — emoji breaks cp932 terminals.

### 9. Incremental adoption
A legacy codebase should not have to fix everything before turning the gate
on. `psc baseline generate` captures today's state; from then on, only *new*
violations fail. Stale baseline entries are flagged so the baseline shrinks
over time.

### 10. The skill must pass its own gate
"Guardian of Quality" loses meaning the moment our own code skirts the rules.
Every change to this skill is gated by the same `psc gate` it ships.

## Configuration

Project rules live under `[tool.python_safe_coding]` in `pyproject.toml`:

```toml
[tool.python_safe_coding]
conflict_rules = [
    { packages = ["darts", "neuralprophet"], reason = "Lightning version clash" },
]
```

## Windows setup (PowerShell)

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```
