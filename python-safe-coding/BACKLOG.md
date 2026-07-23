# Backlog

## Done (2026-04-28)

### Hardening pass (commit f024a8f)
- [x] Fix SKILL.md trailing corruption.
- [x] AST checker: track datetime imports; only flag real `datetime.now()`
      *(later removed entirely — see ADR 0001).*
- [x] `replace_code` includes decorator span; supports `Class.method`.
- [x] Remove `shell=True` from gate runner; use argv lists everywhere.
- [x] Replace `print()` with stdlib `logging`; remove `Any` from editor.
- [x] Self-healer runs Ruff + MyPy + pytest before auto-commit.
- [x] Move `S101` ignore to per-file; per-file rules for scripts/tests.
- [x] Extend Ruff with DTZ/PD/PTH/RUF/ANN/T20/TRY/LOG/G/BLE/RET/PIE.
- [x] Coverage floor 50 → 80; pre_push reads conflict rules from pyproject.
- [x] Emoji → ASCII tags `[OK]`/`[FAIL]`/`[ERROR]` for cp932 safety.
- [x] Test expansion: decorator/async/class replace, AST guards, conflict rules.

### Refactor pass (commit 8000c5c)
- [x] **A-1** Unified `psc` CLI (gate / ast / replace / heal / prepush).
- [x] **A-2** AST checker reduced to Polars-First only; datetime delegated to Ruff DTZ005.
- [x] **A-3** Diff-aware mode (`--since <ref>`) for Ruff and AST checker.
- [x] **A-5** `psc heal --dry-run` / `--patch-only PATH`.
- [x] **B-1** mutmut removed (Windows-blocked, no signal).
- [x] **B-2** `google-genai` moved to `[heal]` extras with lazy import.

### Baselines + CI + docs (commit 9f109ce)
- [x] **A-4** AST-only baseline (`.psc-baseline.json`); `psc baseline {generate,regenerate,diff}`.
- [x] CLI signature: `psc ast` accepts multiple targets (pre-commit prereq).
- [x] **#5** GitHub Actions workflow + pre-commit hooks + templates.
- [x] **#10** SKILL.md split into philosophy + `docs/reference/` + `docs/adr/`.

### Performance (commit 1269a14)
- [x] **#8** Parallel AST walk (ThreadPoolExecutor) + opt-in `--cache-dir` cache
      keyed by `(path, mtime, size, _CHECKER_VERSION)`.

## Remaining (P2 — see ROADMAP.md)
- [ ] **#4** Plugin model via `entry_points` for custom AST rules.
- [ ] **#7** structlog migration + JUnit XML emitter.
- [ ] **#11** Cross-skill adoption playbook (`docs/migration.md`).
- [ ] **A-6** Property-based tests via Hypothesis.
- [ ] **A-7** SBOM (cyclonedx-py) + sigstore release signing.
- [ ] **#12** SLSA posture: gitleaks, pip-audit, OIDC sigstore.
