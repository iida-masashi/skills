# ADR 0003 — Self-Healer as Optional Extra

- **Status**: Accepted (2026-04-28)
- **Deciders**: python-safe-coding maintainers

## Context

The self-healer (`psc heal`) calls Gemini via `google-genai`. Originally this
SDK was a hard dependency of the skill. Two problems:

- Every consumer of `psc gate` paid for the Vertex AI SDK download even if
  they never used `heal`.
- "Quality gate" and "LLM-driven code rewriting" are different responsibility
  domains. Bundling them blurs the value proposition.

## Decision

`google-genai` and `python-dotenv` are moved to
`[project.optional-dependencies].heal`. Install with:

```
uv pip install -e '.[heal]'
```

The healer module imports `google-genai` lazily inside `_import_genai()`. If
the import fails, `HealerDependencyError` is raised with a friendly install
hint, and `psc heal` exits with code 3 (configuration error).

## Consequences

### Positive
- Base install is significantly smaller and faster.
- Consumers who don't want LLM-touched code can simply not install `[heal]`.
- The import boundary makes it easy to swap providers later (e.g.,
  Anthropic Claude) without touching the rest of the skill.

### Negative
- Tests for healer cannot run on the base install (they need `[heal]`).
- We accept this; CI runs both `[base]` and `[heal]` install matrices.

## Future considerations

- A separate `python-safe-coding-healer` package is on the table once a
  second provider is added. For now, keeping it in-tree under an extra is
  cheaper.
