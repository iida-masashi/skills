"""Unified `psc` command-line interface.

Subcommands:
    psc gate     — run Ruff + MyPy + AST policy + pytest with coverage floor.
    psc ast      — run only the Polars-First AST policy checker.
    psc replace  — AST-based safe code replacement (used to be smart_editor).
    psc heal     — self-healing loop (requires [heal] extras).
    psc prepush  — syntax compile + uv lock check + project conflict rules.

Diff-aware mode (`--since <ref>`) limits Ruff and the AST checker to files
changed relative to a git ref. MyPy stays full-tree because per-file mypy
breaks cross-module type inference.

Exit codes:
    0  pass
    1  policy/test violation
    2  internal/runtime error
    3  config error (missing toml, missing extras, etc.)
"""

from __future__ import annotations

import argparse
import compileall
import logging
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from python_safe_coding.ast_checker import _SKIP_PARTS, check_target
from python_safe_coding.baseline import (
    DEFAULT_BASELINE_FILE,
    filter_new,
    fingerprint_all,
    read_baseline,
    write_baseline,
)
from python_safe_coding.editor import replace_code
from python_safe_coding.gate import (
    StepResult,
    ToolUnavailableError,
    run_command,
    write_github_summary,
)

logger = logging.getLogger("psc")

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_INTERNAL = 2
EXIT_CONFIG = 3

DEFAULT_COVERAGE_FLOOR = 80


# --------------------------------------------------------------------------
# Diff-aware helper
# --------------------------------------------------------------------------


def _changed_python_files(since: str, root: Path) -> list[Path] | None:
    """Return .py files changed since `since` ref. None on git failure."""
    try:
        result = subprocess.run(
            # `-c core.quotepath=false` keeps non-ASCII (e.g. cp932) names
            # un-escaped; `--relative` emits paths relative to `cwd=root` (and
            # scopes the diff to that subtree), so `root / line` resolves
            # correctly even when root is a subdirectory of the repo. See
            # docs/DEEP_AUDIT_2026-06-04.md C-1.
            [
                "git",
                "-c",
                "core.quotepath=false",
                "diff",
                "--name-only",
                "--diff-filter=AMR",
                "--relative",
                f"{since}...HEAD",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(root),
        )
    except (FileNotFoundError, OSError):
        logger.warning("git not available; running full scan.")
        return None
    if result.returncode != 0:
        logger.warning(
            "git diff failed (%s); running full scan.", result.stderr.strip()
        )
        return None
    return [
        root / line.strip()
        for line in result.stdout.splitlines()
        if line.strip().endswith(".py") and (root / line.strip()).exists()
    ]


# --------------------------------------------------------------------------
# `psc gate`
# --------------------------------------------------------------------------


def _resolve_gate_targets(args: argparse.Namespace) -> list[str] | None:
    """Resolve which targets Ruff/AST should scan. None = skip those steps."""
    if not args.since:
        return [args.target]
    changed = _changed_python_files(args.since, Path(args.target).resolve())
    if changed is None:
        return [args.target]
    if not changed:
        logger.info("[OK] No Python changes since %s; skipping Ruff/AST.", args.since)
        return None
    targets = [str(p) for p in changed]
    logger.info(
        "Diff-aware: %d file(s) changed since %s.",
        len(targets),
        args.since,
    )
    return targets


def _collect_ast_errors(
    targets: list[str],
    *,
    cache_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    for t in targets:
        errors.extend(check_target(Path(t), cache_dir=cache_dir))
    return errors


def _apply_baseline(
    errors: list[str],
    baseline_path: Path | None,
    root: Path,
) -> tuple[list[str], list[str]]:
    """Return (errors_to_report, info_messages). Empty baseline_path = no filter."""
    info: list[str] = []
    if baseline_path is None or not baseline_path.exists():
        return errors, info
    try:
        baseline = read_baseline(baseline_path)
    except (ValueError, OSError) as exc:
        info.append(f"[WARN] Could not read baseline {baseline_path}: {exc}")
        return errors, info
    new, stale = filter_new(errors, baseline, root=root)
    if stale:
        info.append(
            f"[INFO] Baseline has {len(stale)} stale entries (already-fixed). "
            f"Run `psc baseline regenerate` to clean."
        )
    return new, info


def _step_ast(
    targets: list[str],
    summary: list[StepResult] | None,
    *,
    baseline_path: Path | None = None,
    root: Path,
) -> bool:
    logger.info("Polars-First AST policy...")
    ast_errors = _collect_ast_errors(targets)
    ast_errors, info = _apply_baseline(ast_errors, baseline_path, root)
    for line in info:
        logger.info(line)
    if ast_errors:
        for e in ast_errors:
            sys.stdout.write(e + "\n")
        if summary is not None:
            summary.append(
                StepResult(
                    step="AST Policy",
                    status="Failed",
                    details="\n".join(ast_errors),
                )
            )
        return False
    if summary is not None:
        summary.append(StepResult(step="AST Policy", status="Passed", details=""))
    return True


def _cmd_gate(args: argparse.Namespace) -> int:
    summary: list[StepResult] | None = [] if args.github_summary else None
    success = True

    targets = _resolve_gate_targets(args)
    baseline_path = Path(args.baseline) if args.baseline else None
    root = Path(args.target).resolve()
    if targets:
        logger.info("Code quality (Ruff)...")
        ok, _ = run_command(
            ["uv", "run", "ruff", "check", *targets], "Code Quality (Ruff)", summary
        )
        success = success and ok
        success = (
            _step_ast(
                targets,
                summary,
                baseline_path=baseline_path,
                root=root,
            )
            and success
        )

    # MyPy always runs full-tree (cross-module inference).
    logger.info("Static type analysis (MyPy strict)...")
    ok, _ = run_command(
        ["uv", "run", "mypy", args.target, "--ignore-missing-imports"],
        "Type Checker (MyPy)",
        summary,
    )
    success = success and ok

    logger.info("Unit tests with coverage floor %d%%...", args.coverage_threshold)
    pytest_argv = [
        "uv",
        "run",
        "pytest",
        args.target,
        f"--cov={args.target}",
        f"--cov-fail-under={args.coverage_threshold}",
    ]
    ok, _ = run_command(pytest_argv, "Unit Tests (Pytest)", summary)
    success = success and ok

    if args.github_summary and summary is not None:
        logger.info("\n--- GitHub Summary ---\n%s", write_github_summary(summary))

    if success:
        logger.info("[OK] Quality gate passed.")
        return EXIT_OK
    logger.error("[FAIL] Quality gate failed.")
    return EXIT_VIOLATION


# --------------------------------------------------------------------------
# `psc ast`
# --------------------------------------------------------------------------


def _cmd_ast(args: argparse.Namespace) -> int:
    raw_targets = args.targets or ["."]
    root = Path(raw_targets[0]).resolve()
    targets: list[str] = list(raw_targets)

    if args.since:
        changed = _changed_python_files(args.since, root)
        if changed is None:
            pass  # full scan fallback already logged
        elif not changed:
            logger.info("[OK] No Python changes since %s.", args.since)
            return EXIT_OK
        else:
            targets = [str(p) for p in changed]

    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    errors = _collect_ast_errors(targets, cache_dir=cache_dir)
    baseline_path = Path(args.baseline) if args.baseline else None
    errors, info = _apply_baseline(errors, baseline_path, root)
    for line in info:
        logger.info(line)

    if errors:
        for e in errors:
            sys.stdout.write(e + "\n")
        return EXIT_VIOLATION
    logger.info("[OK] AST policy checks passed.")
    return EXIT_OK


# --------------------------------------------------------------------------
# `psc baseline`
# --------------------------------------------------------------------------


def _cmd_baseline(args: argparse.Namespace) -> int:
    raw_targets = args.targets or ["."]
    root = Path(raw_targets[0]).resolve()
    out_path = Path(args.output)
    cache_dir = Path(args.cache_dir) if args.cache_dir else None

    if args.action in {"generate", "regenerate"}:
        errors = _collect_ast_errors(list(raw_targets), cache_dir=cache_dir)
        fps = fingerprint_all(errors, root=root)
        write_baseline(out_path, fps)
        logger.info("[OK] Baseline written to %s (%d entries).", out_path, len(fps))
        return EXIT_OK

    if args.action == "diff":
        errors = _collect_ast_errors(list(raw_targets), cache_dir=cache_dir)
        try:
            baseline = read_baseline(out_path)
        except (ValueError, OSError):
            logger.exception("[FAIL] Cannot read baseline %s.", out_path)
            return EXIT_CONFIG
        new, stale = filter_new(errors, baseline, root=root)
        for e in new:
            sys.stdout.write(e + "\n")
        if stale:
            logger.info("[INFO] %d stale baseline entries.", len(stale))
        if new:
            return EXIT_VIOLATION
        logger.info("[OK] No new violations vs baseline.")
        return EXIT_OK

    logger.error("Unknown baseline action: %s", args.action)
    return EXIT_CONFIG


# --------------------------------------------------------------------------
# `psc replace`
# --------------------------------------------------------------------------


def _cmd_replace(args: argparse.Namespace) -> int:
    try:
        replace_code(args.file, args.target, args.new_code)
    except (FileNotFoundError, ValueError, SyntaxError):
        logger.exception("[FAIL] Replace failed.")
        return EXIT_VIOLATION
    except OSError:
        # write_text on a read-only/locked file (common on Windows) raises
        # PermissionError/OSError — surface as a clean exit, not a traceback.
        logger.exception("[FAIL] Could not write target file.")
        return EXIT_VIOLATION
    return EXIT_OK


# --------------------------------------------------------------------------
# `psc heal` (lazy import — [heal] extras may be absent)
# --------------------------------------------------------------------------


def _cmd_heal(args: argparse.Namespace) -> int:
    try:
        from python_safe_coding.healer import HealerDependencyError, self_heal_code
    except ImportError:
        logger.exception("[FAIL] Cannot import healer module.")
        return EXIT_INTERNAL

    if args.log:
        log_content = args.log
    elif args.file:
        try:
            log_content = Path(args.file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.exception("[FAIL] Cannot read log file %s.", args.file)
            return EXIT_CONFIG
    else:
        log_content = sys.stdin.read()
    if not log_content.strip():
        logger.error("No error log provided.")
        return EXIT_CONFIG

    patch_path = Path(args.patch_only) if args.patch_only else None
    try:
        ok = self_heal_code(
            log_content,
            auto_commit=args.auto_commit,
            dry_run=args.dry_run,
            patch_only=patch_path,
        )
    except HealerDependencyError:
        logger.exception("[FAIL] [heal] extras not installed.")
        return EXIT_CONFIG
    return EXIT_OK if ok else EXIT_VIOLATION


# --------------------------------------------------------------------------
# `psc prepush`
# --------------------------------------------------------------------------


def _normalize_dep(dep: str) -> str:
    for sep in (">", "<", "=", "~", "!", "[", ";"):
        dep = dep.split(sep, 1)[0]
    return dep.strip().lower()


def evaluate_conflicts(toml_path: Path) -> tuple[bool, list[str]]:
    """Evaluate `[tool.python_safe_coding].conflict_rules` against declared deps.

    Returns (ok, violation_messages). ok==True when no rule fires.
    Missing pyproject.toml is treated as a pass.
    """
    if not toml_path.exists():
        return True, []
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    deps = {
        _normalize_dep(d) for d in data.get("project", {}).get("dependencies", []) or []
    }
    rules = (
        data.get("tool", {}).get("python_safe_coding", {}).get("conflict_rules", [])
        or []
    )
    violations: list[str] = []
    for rule in rules:
        packages = {p.lower() for p in rule.get("packages", [])}
        if packages and packages.issubset(deps):
            reason = rule.get("reason", "Conflicting packages declared together.")
            violations.append(f"Conflict {sorted(packages)}: {reason}")
    return not violations, violations


def _cmd_prepush(args: argparse.Namespace) -> int:
    root = Path(args.target).resolve()
    logger.info("--- Pre-push quality gate ---")

    logger.info("[1/3] Compile-check across %s", root)
    # Skip vendored/build dirs (mirrors ast_checker._SKIP_PARTS) so a broken
    # .py inside a dependency or build artifact does not fail our own gate.
    skip_rx = re.compile(
        r"[\\/](?:" + "|".join(re.escape(p) for p in _SKIP_PARTS) + r")[\\/]"
    )
    syntax_ok = bool(compileall.compile_dir(str(root), quiet=1, rx=skip_rx))
    if not syntax_ok:
        logger.error("[FAIL] Syntax errors. Run 'python -m compileall .'.")

    logger.info("[2/3] uv.lock sync...")
    res = subprocess.run(
        ["uv", "lock", "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    lock_ok = res.returncode == 0
    if not lock_ok:
        logger.error("[FAIL] uv.lock out of sync. Run 'uv lock'.")

    logger.info("[3/3] Conflict rules...")
    try:
        conflicts_ok, violations = evaluate_conflicts(root / "pyproject.toml")
    except (OSError, tomllib.TOMLDecodeError):
        logger.exception("[FAIL] Cannot parse pyproject.toml.")
        return EXIT_CONFIG
    for v in violations:
        logger.error("[FAIL] %s", v)

    if syntax_ok and lock_ok and conflicts_ok:
        logger.info("[OK] Cleared for push.")
        return EXIT_OK
    return EXIT_VIOLATION


# --------------------------------------------------------------------------
# Argument parser
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="psc", description="Python Safe Coding — Guardian of Quality"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_gate = sub.add_parser("gate", help="Run the full quality gate")
    p_gate.add_argument("--target", default=".", help="Target directory or file")
    p_gate.add_argument(
        "--since", help="Limit Ruff/AST to files changed since git <ref>"
    )
    p_gate.add_argument(
        "--coverage-threshold", type=int, default=DEFAULT_COVERAGE_FLOOR
    )
    p_gate.add_argument("--github-summary", action="store_true")
    p_gate.add_argument(
        "--baseline",
        help=f"AST-policy baseline file (e.g. {DEFAULT_BASELINE_FILE}); "
        "only NEW violations fail the gate.",
    )
    p_gate.set_defaults(func=_cmd_gate)

    p_ast = sub.add_parser("ast", help="Run only the AST policy checker")
    p_ast.add_argument(
        "targets",
        nargs="*",
        default=["."],
        help="One or more files/directories (pre-commit passes file list)",
    )
    p_ast.add_argument("--since", help="Limit to files changed since git <ref>")
    p_ast.add_argument(
        "--baseline",
        help="Suppress violations listed in this baseline file",
    )
    p_ast.add_argument(
        "--cache-dir",
        help="Directory for per-file result cache (e.g. .psc-cache). "
        "Off by default; opt in for speedups on large repos.",
    )
    p_ast.set_defaults(func=_cmd_ast)

    p_bl = sub.add_parser("baseline", help="Generate or diff an AST policy baseline")
    p_bl.add_argument(
        "action",
        choices=["generate", "regenerate", "diff"],
        help="generate: write fresh baseline; diff: list new violations",
    )
    p_bl.add_argument(
        "targets",
        nargs="*",
        default=["."],
        help="Files/directories to scan",
    )
    p_bl.add_argument(
        "--output",
        "-o",
        default=DEFAULT_BASELINE_FILE,
        help=f"Baseline file path (default {DEFAULT_BASELINE_FILE})",
    )
    p_bl.add_argument(
        "--cache-dir",
        help="Directory for per-file result cache (e.g. .psc-cache).",
    )
    p_bl.set_defaults(func=_cmd_baseline)

    p_rep = sub.add_parser("replace", help="AST-based safe code replacement")
    p_rep.add_argument("--file", required=True)
    p_rep.add_argument(
        "--target", required=True, help="Function/class name (use 'Class.method')"
    )
    p_rep.add_argument("--new-code", required=True)
    p_rep.set_defaults(func=_cmd_replace)

    p_heal = sub.add_parser("heal", help="Self-healing loop (requires [heal] extras)")
    p_heal.add_argument("--log", help="Inline error log string")
    p_heal.add_argument("--file", help="Path to a log file (else read stdin)")
    p_heal.add_argument("--auto-commit", action="store_true")
    p_heal.add_argument(
        "--dry-run", action="store_true", help="Print diff; do not modify file"
    )
    p_heal.add_argument("--patch-only", help="Write diff to PATH; do not modify file")
    p_heal.set_defaults(func=_cmd_heal)

    p_pp = sub.add_parser(
        "prepush", help="Pre-push checks: compile, uv lock, conflict rules"
    )
    p_pp.add_argument("--target", default=".")
    p_pp.set_defaults(func=_cmd_prepush)

    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        sys.exit(args.func(args))
    except ToolUnavailableError:
        # Missing launcher (e.g. `uv`) is an environment/config problem, not a
        # code violation — route to EXIT_CONFIG so CI can tell them apart.
        logger.exception("[FAIL] Required tool is unavailable.")
        sys.exit(EXIT_CONFIG)
    except Exception:
        # Any unanticipated failure is an internal gate bug; surface the
        # documented exit code instead of a raw traceback.
        logger.exception("[ERROR] Internal error in psc.")
        sys.exit(EXIT_INTERNAL)


if __name__ == "__main__":
    main()
