# `psc` — Command Reference

All subcommands honour the [exit-code contract](exit-codes.md).

## `psc gate`

Run the full quality gate: Ruff → AST policy → MyPy → pytest.

```
psc gate [--target PATH] [--since REF] [--baseline FILE]
         [--coverage-threshold N] [--github-summary]
```

| Flag | Default | Effect |
|------|---------|--------|
| `--target` | `.` | Directory or file to scan. |
| `--since REF` | (off) | Diff-aware: only `.py` files changed against `REF` are passed to Ruff and the AST checker. MyPy stays full-tree because per-file mypy breaks cross-module inference. Falls back to a full scan with a warning when `git` is unavailable. |
| `--baseline FILE` | (off) | Suppress AST-policy violations recorded in `FILE`. Only NEW violations fail. |
| `--coverage-threshold N` | `80` | Pytest fails if total coverage < N%. |
| `--github-summary` | (off) | Append a markdown summary to `$GITHUB_STEP_SUMMARY`. |

## `psc ast`

Run only the Polars-First AST policy.

```
psc ast [TARGET ...] [--since REF] [--baseline FILE]
```

`TARGET` accepts multiple positional arguments — pre-commit passes the list of
changed files this way. Defaults to `.` if no target is given.

| Flag | Effect |
|------|--------|
| `--baseline FILE` | Suppress violations recorded in `FILE`. |
| `--cache-dir DIR` | Cache per-file results under `DIR` (e.g. `.psc-cache`). Off by default. Cache key is `(path, mtime, size, _CHECKER_VERSION)`; bumping the checker version invalidates everything automatically. Add `DIR` to `.gitignore`. |

## `psc baseline`

Manage the AST-policy baseline.

```
psc baseline generate [TARGET ...] [--output FILE]
psc baseline regenerate [TARGET ...] [--output FILE]
psc baseline diff [TARGET ...] [--output FILE]
```

| Action | Effect |
|--------|--------|
| `generate` / `regenerate` | Scan `TARGET`, write fingerprints to `FILE` (default `.psc-baseline.json`). Existing file is overwritten. |
| `diff` | Scan `TARGET`, print violations not in `FILE`. Exits 1 if any new violation, 0 otherwise. Stale baseline entries are reported on stderr. |

Fingerprint format: `(file_path, rule_id, sha1_of_offending_line[:16])`. Hashing
the line content (rather than line numbers) means the baseline survives
reformats and unrelated edits above the offending line.

`psc baseline` also accepts `--cache-dir DIR` with the same semantics as
`psc ast`.

## `psc replace`

AST-based safe code replacement.

```
psc replace --file FILE --target NAME --new-code FILE
```

`--target` is the function or class name. Use `Class.method` for nested
targets. Decorators are part of the replaced span — replacing a decorated
function does not leave orphan `@decorator` lines.

## `psc heal`

Self-healing loop. Requires the `[heal]` extras (`uv pip install -e '.[heal]'`).

```
psc heal [--log STR | --file PATH | -]
         [--auto-commit | --dry-run | --patch-only PATH]
```

Reads an error log (inline, file, or stdin), asks Gemini for a fix, and
either:

| Mode | Effect |
|------|--------|
| (default) | Write fix, run Ruff + MyPy + pytest, optionally commit. Reverts on failure. |
| `--dry-run` | Print a unified diff to stdout. Do not modify the file. |
| `--patch-only PATH` | Write the diff to `PATH`. Apply later with `git apply PATH`. |
| `--auto-commit` | After validation passes, `git commit` with a `bot(heal):` message. |

When the `[heal]` extras are missing, `psc heal` exits with code 3 and a
hint pointing at the install command.

## `psc prepush`

Pre-push reproducibility checks.

```
psc prepush [--target PATH]
```

Runs three checks in sequence:

1. `compileall` over `TARGET` — catches syntax errors before push.
2. `uv lock --check` — catches drift between `pyproject.toml` and `uv.lock`.
3. Project conflict rules from `[tool.python_safe_coding].conflict_rules`.

Exits 1 on any failure.
