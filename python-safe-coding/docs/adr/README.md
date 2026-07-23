# Architecture Decision Records

We use lightweight ADRs to capture decisions whose rationale is easy to lose.
Format follows [Michael Nygard's template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

## Index

| # | Title | Status |
|---|-------|--------|
| [0001](0001-ruff-first-policy.md) | Ruff-First Policy Enforcement | Accepted |
| [0002](0002-ast-only-baseline.md) | AST-Only Baseline (No Ruff Baseline on First Pass) | Accepted |
| [0003](0003-healer-as-optional-extra.md) | Self-Healer as Optional Extra | Accepted |
| [0004](0004-thread-pool-and-mtime-cache.md) | ThreadPool + mtime/size cache for AST checker | Accepted |

## When to write a new ADR

- A non-obvious decision was made (the obvious choice would have been wrong).
- A decision will be hard to reverse (architectural).
- A future maintainer is likely to ask "why did they do it *this* way?".

Skip ADRs for trivial choices, day-to-day refactors, or anything covered by
existing rules in `[tool.ruff.lint]` or `SKILL.md`.
