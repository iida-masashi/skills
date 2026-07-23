# Lessons Learned

## 2026-04-28 — Baselines, parallel AST, cache

- **Cache invalidation on rule changes is the silent-failure mode.** A cache
  keyed only on `(path, mtime, size)` will silently reuse yesterday's "clean"
  verdict under today's stricter rules — green CI on broken code. Bake a
  `_CHECKER_VERSION` into the key (mirror `BASELINE_VERSION`) and bump it
  whenever a rule changes. mtime+size is what `make`/`ninja` use; do not
  hash file contents per run.
- **ThreadPool over ProcessPool for `ast.parse`.** The C parser releases the
  GIL, so threads scale fine without the spawn overhead ProcessPool incurs
  on Windows for typical (<100 file) repos.
- **Threshold the parallelism.** Below ~16 files, pool spin-up costs more
  than the parallel gain. Default to single-threaded for small scans.
- **Sort parallel output by path.** `pool.map` happens to preserve order
  today, but making it explicit at the end of `check_target` keeps `psc ast`
  diffs reproducible across reruns.
- **Cache failures must never fail a check.** `store(...)` swallows
  `OSError` (disk full, permission denied) silently. Otherwise a flaky
  filesystem becomes a flaky CI gate.
- **Default cache=off (opt-in via flag).** "Why isn't psc seeing my fix?"
  is one of the most expensive support questions. Mirror `--baseline`:
  predictable by default, opt-in for the speedup.
- **Baseline scope on the first pass: AST-checker only.** Coupling the
  baseline format to Ruff's `--output-format=json` schema means schema
  bumps in upstream Ruff silently invalidate the baseline. We control our
  own AST messages; we don't control Ruff's. Ship AST-only first; revisit.
- **Fingerprint by line content, not line number.** `(file, rule_id,
  sha1(line)[:16])` survives reformats and unrelated edits above the
  violation; a line-number fingerprint dies on the next `ruff format`.
- **Pre-commit's `pass_filenames` semantics drive the CLI.** Pre-commit
  invokes hooks as `psc ast file1.py file2.py ...`. Not anticipating that
  meant a v0.3 patch to swap `target` (singular `nargs="?"`) for
  `targets` (`nargs="*"`). Decide CLI signatures with the eventual hook
  invocation in mind.
- **Don't write cookbooks for targets you can't compile-test.** Recipes
  in `docs/cookbook/` for skills that aren't yet psc-aware become
  vaporware. Defer until a target is actually adopted.

## 2026-04-28 — Guardian-of-Quality hardening pass

- **AST `.now()` matching is naming-sensitive.** Matching every `.now()`
  falsely flags `pendulum.now()`, `Cache.now()`, etc. *(Subsequently
  replaced entirely by Ruff DTZ005 — see ADR 0001. The lesson stands as
  a record of why we tried to track bindings before deciding it was simpler
  to delegate.)*
- **`FunctionDef.lineno` does not include decorators.** `replace_code` must
  start the span at `min(node.lineno, node.decorator_list[0].lineno)` or
  decorators become orphan lines after replacement.
- **`shell=True` is a footgun even with a `# nosec`.** Any user-supplied
  `--target` is interpreted as shell metacharacters. Argv lists eliminate
  that class entirely; pair with Ruff `S603` per-file-ignore on the trusted
  wrapper instead of suppressing it inline.
- **Self-healer must clear the *full* quality bar, not just Ruff.** Auto-
  committing LLM-generated code that only passed lint can introduce silent
  type errors and broken tests into history. Always run mypy + pytest before
  the commit; revert the file on any failure.
- **Per-file Ruff ignores beat global ones.** `S101` (assert) belongs only
  in `tests/`; `LOG015`/`TRY401` in CLI scripts; `S603`/`S607` in subprocess
  wrappers. Global ignores are how you smuggle bad patterns into `src/`.
- **Emoji breaks cp932.** Project CLAUDE.md flagged this; we still shipped
  ✅❌🚑 in our own tools. ASCII tags (`[OK]`, `[FAIL]`, `[ERROR]`) are
  the durable choice.
- **Documentation drift recurs.** SKILL.md required `print()` to be replaced
  by `structlog`, yet the same file's tools still used `print()`. Whenever
  a rule lands in SKILL.md, audit *this* skill for compliance first.
- **Trust Ruff first.** Naive `datetime.now()` is delegated to `DTZ005`,
  bare `except:` to `BLE001`. Custom AST rules exist only for what Ruff
  cannot express (currently: Polars First). Adding a Ruff category is
  leverage; adding a custom rule is debt. (ADR 0001.)

## 2026-04-16
- **Documentation drift**: The original SKILL.md described practices (`src/`
  layout, TDD, `BACKLOG.md`) that were not yet implemented. Closed the gap
  by restructuring the package and adding tracking files.
