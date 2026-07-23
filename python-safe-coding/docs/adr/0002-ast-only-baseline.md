# ADR 0002 — AST-Only Baseline (No Ruff Baseline on First Pass)

- **Status**: Accepted (2026-04-28)
- **Deciders**: python-safe-coding maintainers

## Context

The baseline feature (`.psc-baseline.json`) lets legacy codebases turn the
gate on without fixing every existing violation up front. The natural
question is: should the baseline cover Ruff violations too, not just our AST
checker's?

## Decision

**Baseline scope is AST-checker violations only on the first pass.**

Ruff baselines are deferred. Reasons:

- Ruff has its own evolving JSON output format
  (`--output-format=json`). Coupling our baseline format to it means schema
  changes in upstream Ruff silently break our baseline.
- Our own violation messages are a single line of text we control, easy to
  fingerprint by `(file, rule_id, line_content_hash)`.
- The number of custom AST rules is small (one). Falling behind on Ruff
  baselines is a much larger backlog than falling behind on `polars-first`.

If a consumer wants Ruff baselining, we recommend a separate tool today
(e.g., a CI script that diffs Ruff JSON against a stored snapshot). We may
revisit once Ruff publishes a versioned schema.

## Fingerprint design

`(file_path, rule_id, sha1(offending_line)[:16])`

- **`file_path`** — relative to `--target` so baselines work on any
  checkout location.
- **`rule_id`** — short stable identifier (e.g., `polars-first`), classified
  from the message prefix. Insulates against message wording changes.
- **`line_hash`** — SHA-1 prefix of the *content* of the offending line,
  not its line number. Reformatting (`ruff format`) shifts line numbers
  without changing semantics; we want the baseline to survive that.

## Stale entries

When a violation is fixed but its baseline entry is not removed, we report
the entry as *stale* (visible in `psc gate` and `psc baseline diff` output).
Stale entries do not fail the gate but accumulate as a maintenance smell;
`psc baseline regenerate` removes them.

## Consequences

### Positive
- Baseline format is small, readable, version-pinned (`"version": 1`).
- Adoption story: one command (`psc baseline generate`) for any legacy repo.
- Stale-entry detection gives a free signal that the baseline is shrinking
  over time, which is the goal.

### Negative
- Ruff baselining must be solved separately by adopters, until we revisit.
- The format will need a version bump if we extend the fingerprint shape.
