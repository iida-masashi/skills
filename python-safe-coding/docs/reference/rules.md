# Policy Rules

`psc` enforces three layers of policy. Knowing where each rule lives helps you
edit the right config when you need to silence or extend it.

## Layer 1 — Ruff

Configured in `pyproject.toml` under `[tool.ruff.lint]`. Categories enabled:

| Cat. | Covers |
|------|--------|
| `E`, `F`, `W` | pycodestyle / pyflakes basics |
| `I` | isort (import order) |
| `UP` | pyupgrade (modern syntax) |
| `B` | bugbear (common Python footguns; includes mutable-default `B006`) |
| `SIM` | simplification opportunities |
| `C90` | mccabe complexity (max 10) |
| `S` | bandit security (e.g. `shell=True`, hardcoded passwords) |
| `DTZ` | timezone-aware datetime (`DTZ005` = naive `datetime.now()`) |
| `PD` | pandas-vet (usage warnings on legitimate pandas use) |
| `PTH` | `pathlib` over `os.path` |
| `RUF` | Ruff-native checks |
| `ANN` | type annotation coverage |
| `T20` | `print()` detection |
| `TRY` | exception-handling best practices |
| `LOG`, `G` | logging hygiene |
| `BLE` | blind `except:` |
| `RET` | return-statement smells |
| `PIE` | misc. |

Per-file ignores (`[tool.ruff.lint.per-file-ignores]`) relax constraints in
test code and CLI entry points only.

## Layer 2 — MyPy strict

Configured in `pyproject.toml` under `[tool.mypy]`. All strict flags enabled:
`disallow_untyped_defs`, `warn_return_any`, `no_implicit_optional`, etc. The
gate runs `mypy --ignore-missing-imports` so third-party packages without
stubs do not cascade-fail.

## Layer 3 — Custom AST policy

Implemented in `src/python_safe_coding/ast_checker.py`. Currently one rule:

| Rule ID | Detects | Replacement |
|---------|---------|-------------|
| `polars-first` | `import pandas`, `from pandas import ...` | Use Polars. |

Custom AST rules exist only when Ruff cannot express the policy. `polars-first`
is custom because Ruff's `PD` category warns about pandas *usage patterns*,
not about importing pandas at all.

When you propose a new custom rule, first check whether Ruff already has it
([Ruff rule index](https://docs.astral.sh/ruff/rules/)) — adding a custom rule
is debt; adding a Ruff category is leverage.

## Layer 4 — Project conflict rules

Configured in consumer projects under `[tool.python_safe_coding].conflict_rules`.
Each rule fires when *all* listed packages appear in `[project.dependencies]`:

```toml
[tool.python_safe_coding]
conflict_rules = [
    { packages = ["darts", "neuralprophet"], reason = "Lightning version clash" },
]
```

`psc prepush` evaluates these on every run.
