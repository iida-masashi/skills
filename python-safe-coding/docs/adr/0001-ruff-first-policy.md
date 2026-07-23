# ADR 0001 — Ruff-First Policy Enforcement

- **Status**: Accepted (2026-04-28)
- **Deciders**: python-safe-coding maintainers

## Context

The first version of this skill shipped a custom AST visitor that detected
naive `datetime.now()` calls and `import pandas`. Both were policy rules we
cared about. The visitor grew complex enough to falsely flag `pendulum.now()`
and arbitrary user-defined `.now()` methods, leading to a v0.2 patch that
tracked module bindings to disambiguate.

Around the same time, we evaluated Ruff's `DTZ005` rule and found it already
handled every binding form (`from datetime import datetime`, `import datetime`,
aliases) more thoroughly than our visitor.

## Decision

**Custom AST rules exist only when Ruff cannot express the policy.**

- Naive `datetime.now()` detection is delegated to Ruff `DTZ005`. The custom
  visitor for it has been removed.
- The custom AST checker is kept, but scoped to a single rule (`polars-first`,
  banning `import pandas`). Ruff's `PD` category warns about pandas *usage
  patterns* on legitimate pandas use; it does not ban the import itself, so
  this rule cannot be expressed in Ruff today.
- New custom rules require justification: "Why can't this be a Ruff rule or a
  Ruff config?" If the answer is "it can," add it to `[tool.ruff.lint]` and do
  not write a visitor.

## Consequences

### Positive
- Visitor code shrank ~60% (one rule instead of three plus binding tracking).
- We inherit Ruff's release cadence and false-positive fixes for free.
- Adding a Ruff category is a one-line config change; adding a visitor rule
  is ~30 lines plus tests.
- Users who already know Ruff do not need to learn a parallel rule namespace.

### Negative
- Some policies *will* require a custom rule (e.g., banning a specific
  internal import pattern). We accept this on a case-by-case basis with the
  justification above.
- We are coupled to Ruff's behaviour for the rules we delegate. A future
  Ruff release could change `DTZ005` semantics. We treat this as acceptable
  because: (a) Ruff's compatibility track record is good, (b) we pin the
  version in `uv.lock`, and (c) we test against our own delegated rules.

## Alternatives considered

1. **Keep the custom visitor for everything** — rejected; reinventing Ruff is
   not the value proposition.
2. **Drop the custom visitor entirely** — rejected; `polars-first` cannot be
   expressed in Ruff today.
3. **Build a plugin system for custom rules** — deferred to a future ADR.
   Premature with only one custom rule.
