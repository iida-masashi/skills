"""Tests for the unified `psc` CLI."""

from __future__ import annotations

import compileall
import io
import subprocess
from pathlib import Path
from typing import Any

import pytest

from python_safe_coding import cli
from python_safe_coding.gate import ToolUnavailableError

# ---------- helpers --------------------------------------------------------


class _FakeProc:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ---------- _normalize_dep -------------------------------------------------


def test_normalize_dep_strips_versions_and_extras() -> None:
    assert cli._normalize_dep("ruff>=0.5.0") == "ruff"
    assert cli._normalize_dep("mypy~=1.10") == "mypy"
    assert cli._normalize_dep("pytest-cov[toml]") == "pytest-cov"
    assert cli._normalize_dep("Polars==1.0; python_version>='3.12'") == "polars"


# ---------- evaluate_conflicts (pure) --------------------------------------


def test_evaluate_conflicts_no_rules(tmp_path: Path) -> None:
    toml = tmp_path / "pyproject.toml"
    toml.write_text(
        '[project]\nname = "x"\ndependencies = ["polars", "ruff"]\n',
        encoding="utf-8",
    )
    ok, violations = cli.evaluate_conflicts(toml)
    assert ok is True
    assert violations == []


def test_evaluate_conflicts_rule_triggers(tmp_path: Path) -> None:
    toml = tmp_path / "pyproject.toml"
    toml.write_text(
        "[project]\n"
        'name = "x"\n'
        'dependencies = ["darts", "neuralprophet"]\n'
        "[tool.python_safe_coding]\n"
        'conflict_rules = [{ packages = ["darts", "neuralprophet"], '
        'reason = "Lightning clash" }]\n',
        encoding="utf-8",
    )
    ok, violations = cli.evaluate_conflicts(toml)
    assert ok is False
    assert len(violations) == 1
    assert "Lightning clash" in violations[0]


def test_evaluate_conflicts_rule_not_triggered(tmp_path: Path) -> None:
    toml = tmp_path / "pyproject.toml"
    toml.write_text(
        "[project]\n"
        'name = "x"\n'
        'dependencies = ["darts"]\n'
        "[tool.python_safe_coding]\n"
        'conflict_rules = [{ packages = ["darts", "neuralprophet"], reason = "x" }]\n',
        encoding="utf-8",
    )
    ok, violations = cli.evaluate_conflicts(toml)
    assert ok is True
    assert violations == []


def test_evaluate_conflicts_missing_toml(tmp_path: Path) -> None:
    ok, violations = cli.evaluate_conflicts(tmp_path / "missing.toml")
    assert ok is True
    assert violations == []


# ---------- _cmd_ast -------------------------------------------------------


def test_cmd_ast_clean(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("import polars\n", encoding="utf-8")
    args = cli._build_parser().parse_args(["ast", str(tmp_path)])
    assert cli._cmd_ast(args) == cli.EXIT_OK


def test_cmd_ast_violation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "bad.py").write_text("import pandas\n", encoding="utf-8")
    args = cli._build_parser().parse_args(["ast", str(tmp_path)])
    assert cli._cmd_ast(args) == cli.EXIT_VIOLATION
    assert "Use polars instead of pandas" in capsys.readouterr().out


def test_cmd_ast_with_since_no_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "bad.py").write_text("import pandas\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_changed_python_files", lambda *_a, **_k: [])
    args = cli._build_parser().parse_args(["ast", str(tmp_path), "--since", "main"])
    assert cli._cmd_ast(args) == cli.EXIT_OK  # no changes -> skip even if pandas exists


def test_cmd_ast_with_since_changes_and_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("import pandas\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_changed_python_files", lambda *_a, **_k: [bad])
    args = cli._build_parser().parse_args(["ast", str(tmp_path), "--since", "main"])
    assert cli._cmd_ast(args) == cli.EXIT_VIOLATION
    assert "Use polars" in capsys.readouterr().out


def test_cmd_ast_with_since_git_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "ok.py").write_text("import polars\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_changed_python_files", lambda *_a, **_k: None)
    args = cli._build_parser().parse_args(["ast", str(tmp_path), "--since", "main"])
    # Falls back to full scan -> clean.
    assert cli._cmd_ast(args) == cli.EXIT_OK


# ---------- _cmd_replace ---------------------------------------------------


def test_cmd_replace_target_not_found(tmp_path: Path) -> None:
    target = tmp_path / "t.py"
    target.write_text("def a(): pass\n", encoding="utf-8")
    new = tmp_path / "new.py"
    new.write_text("def a(): pass\n", encoding="utf-8")
    args = cli._build_parser().parse_args(
        [
            "replace",
            "--file",
            str(target),
            "--target",
            "missing",
            "--new-code",
            str(new),
        ]
    )
    assert cli._cmd_replace(args) == cli.EXIT_VIOLATION


def test_cmd_replace_success(tmp_path: Path) -> None:
    target = tmp_path / "t.py"
    target.write_text("def a():\n    return 1\n", encoding="utf-8")
    new = tmp_path / "new.py"
    new.write_text("def a():\n    return 99\n", encoding="utf-8")
    args = cli._build_parser().parse_args(
        [
            "replace",
            "--file",
            str(target),
            "--target",
            "a",
            "--new-code",
            str(new),
        ]
    )
    assert cli._cmd_replace(args) == cli.EXIT_OK
    assert "return 99" in target.read_text(encoding="utf-8")


# ---------- _changed_python_files (subprocess paths) -----------------------


def test_changed_python_files_handles_no_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*_a: Any, **_kw: Any) -> _FakeProc:
        raise FileNotFoundError("no git")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cli._changed_python_files("main", tmp_path) is None


def test_changed_python_files_handles_git_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*_a: Any, **_kw: Any) -> _FakeProc:
        return _FakeProc(returncode=128, stderr="bad ref")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cli._changed_python_files("nope", tmp_path) is None


def test_changed_python_files_returns_existing_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = tmp_path / "a.py"
    a.write_text("x = 1\n", encoding="utf-8")

    # b.py is reported by git but does not exist on disk -> filtered out.
    def fake_run(*_a: Any, **_kw: Any) -> _FakeProc:
        return _FakeProc(returncode=0, stdout="a.py\nb.py\nREADME.md\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    files = cli._changed_python_files("main", tmp_path)
    assert files == [a]


# ---------- _cmd_prepush (mocked subprocess + compileall) ------------------


def test_cmd_prepush_all_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = []\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(compileall, "compile_dir", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: _FakeProc(returncode=0),
    )
    args = cli._build_parser().parse_args(["prepush", "--target", str(tmp_path)])
    assert cli._cmd_prepush(args) == cli.EXIT_OK


def test_cmd_prepush_lock_out_of_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = []\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(compileall, "compile_dir", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: _FakeProc(returncode=1, stderr="lock"),
    )
    args = cli._build_parser().parse_args(["prepush", "--target", str(tmp_path)])
    assert cli._cmd_prepush(args) == cli.EXIT_VIOLATION


def test_cmd_prepush_conflict_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["darts","neuralprophet"]\n'
        "[tool.python_safe_coding]\n"
        'conflict_rules = [{ packages = ["darts","neuralprophet"], reason = "x" }]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(compileall, "compile_dir", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: _FakeProc(returncode=0),
    )
    args = cli._build_parser().parse_args(["prepush", "--target", str(tmp_path)])
    assert cli._cmd_prepush(args) == cli.EXIT_VIOLATION


# ---------- _cmd_heal (mocked self_heal_code) ------------------------------


def test_cmd_heal_empty_log_returns_config_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    args = cli._build_parser().parse_args(["heal"])
    assert cli._cmd_heal(args) == cli.EXIT_CONFIG


def test_cmd_heal_invokes_self_heal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_heal(error_log: str, **kw: Any) -> bool:
        captured["log"] = error_log
        captured.update(kw)
        return True

    import python_safe_coding.healer as healer_mod

    monkeypatch.setattr(healer_mod, "self_heal_code", fake_heal)
    args = cli._build_parser().parse_args(
        [
            "heal",
            "--log",
            "x.py:1: ERROR: oh",
            "--dry-run",
        ]
    )
    assert cli._cmd_heal(args) == cli.EXIT_OK
    assert captured["dry_run"] is True
    assert captured["auto_commit"] is False


def test_cmd_heal_propagates_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import python_safe_coding.healer as healer_mod

    monkeypatch.setattr(healer_mod, "self_heal_code", lambda *_a, **_kw: False)
    args = cli._build_parser().parse_args(["heal", "--log", "x.py:1: ERROR: oh"])
    assert cli._cmd_heal(args) == cli.EXIT_VIOLATION


# ---------- _cmd_gate (heavy mock: just the dispatch flow) -----------------


def test_cmd_ast_accepts_multiple_targets(tmp_path: Path) -> None:
    """pre-commit passes file lists; psc ast must accept them."""
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("import polars\n", encoding="utf-8")
    b.write_text("import pandas\n", encoding="utf-8")
    args = cli._build_parser().parse_args(["ast", str(a), str(b)])
    assert cli._cmd_ast(args) == cli.EXIT_VIOLATION


def test_cmd_ast_with_baseline_suppresses_known(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("import pandas\n", encoding="utf-8")
    baseline = tmp_path / ".psc-baseline.json"
    # Generate
    gen_args = cli._build_parser().parse_args(
        [
            "baseline",
            "generate",
            str(tmp_path),
            "--output",
            str(baseline),
        ]
    )
    assert cli._cmd_baseline(gen_args) == cli.EXIT_OK
    capsys.readouterr()  # clear

    # Now run ast with the baseline — pandas import is known, no new violations.
    ast_args = cli._build_parser().parse_args(
        [
            "ast",
            str(tmp_path),
            "--baseline",
            str(baseline),
        ]
    )
    assert cli._cmd_ast(ast_args) == cli.EXIT_OK


def test_cmd_baseline_diff_reports_new_violation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    a = tmp_path / "a.py"
    a.write_text("import pandas\n", encoding="utf-8")
    baseline = tmp_path / ".psc-baseline.json"
    cli._cmd_baseline(
        cli._build_parser().parse_args(
            [
                "baseline",
                "generate",
                str(tmp_path),
                "--output",
                str(baseline),
            ]
        )
    )
    capsys.readouterr()

    # Add a new violating file.
    b = tmp_path / "b.py"
    b.write_text("from pandas import DataFrame\n", encoding="utf-8")
    diff_args = cli._build_parser().parse_args(
        [
            "baseline",
            "diff",
            str(tmp_path),
            "--output",
            str(baseline),
        ]
    )
    assert cli._cmd_baseline(diff_args) == cli.EXIT_VIOLATION
    out = capsys.readouterr().out
    assert "b.py" in out


def test_cmd_ast_cache_dir_creates_cache(tmp_path: Path) -> None:
    """--cache-dir populates the directory after a scan."""
    (tmp_path / "ok.py").write_text("import polars\n", encoding="utf-8")
    cache_dir = tmp_path / ".psc-cache"
    args = cli._build_parser().parse_args(
        [
            "ast",
            str(tmp_path),
            "--cache-dir",
            str(cache_dir),
        ]
    )
    assert cli._cmd_ast(args) == cli.EXIT_OK
    assert cache_dir.exists()
    assert any(cache_dir.glob("*.json"))


def test_cmd_baseline_generate_with_cache(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("import polars\n", encoding="utf-8")
    cache_dir = tmp_path / ".psc-cache"
    out = tmp_path / "baseline.json"
    args = cli._build_parser().parse_args(
        [
            "baseline",
            "generate",
            str(tmp_path),
            "--output",
            str(out),
            "--cache-dir",
            str(cache_dir),
        ]
    )
    assert cli._cmd_baseline(args) == cli.EXIT_OK
    assert any(cache_dir.glob("*.json"))


def test_cmd_baseline_diff_clean(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    a.write_text("import pandas\n", encoding="utf-8")
    baseline = tmp_path / ".psc-baseline.json"
    cli._cmd_baseline(
        cli._build_parser().parse_args(
            [
                "baseline",
                "generate",
                str(tmp_path),
                "--output",
                str(baseline),
            ]
        )
    )
    diff_args = cli._build_parser().parse_args(
        [
            "baseline",
            "diff",
            str(tmp_path),
            "--output",
            str(baseline),
        ]
    )
    assert cli._cmd_baseline(diff_args) == cli.EXIT_OK


def test_cmd_gate_diff_aware_no_changes_skips_lint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When --since reports zero changed files, gate must not invoke ruff."""
    monkeypatch.setattr(cli, "_changed_python_files", lambda *_a, **_kw: [])
    calls: list[str] = []

    def fake_run_command(argv: list[str], desc: str, _summary: Any) -> tuple[bool, str]:
        calls.append(desc)
        return True, ""

    monkeypatch.setattr(cli, "run_command", fake_run_command)
    args = cli._build_parser().parse_args(
        [
            "gate",
            "--target",
            str(tmp_path),
            "--since",
            "main",
        ]
    )
    rc = cli._cmd_gate(args)
    assert rc == cli.EXIT_OK
    # MyPy and Pytest still run; Ruff/AST skipped.
    assert "Code Quality (Ruff)" not in calls
    assert "Type Checker (MyPy)" in calls
    assert "Unit Tests (Pytest)" in calls


def test_cmd_gate_full_run_failure_returns_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-4: a full (non-diff) run where a step fails must return EXIT_VIOLATION,
    after invoking Ruff + MyPy + Pytest and the AST step."""
    (tmp_path / "ok.py").write_text("import polars\n", encoding="utf-8")
    calls: list[str] = []

    def fake_run_command(argv: list[str], desc: str, _summary: Any) -> tuple[bool, str]:
        calls.append(desc)
        # Pytest "fails"; everything else passes.
        return (desc != "Unit Tests (Pytest)"), ""

    monkeypatch.setattr(cli, "run_command", fake_run_command)
    args = cli._build_parser().parse_args(["gate", "--target", str(tmp_path)])
    assert cli._cmd_gate(args) == cli.EXIT_VIOLATION
    assert "Code Quality (Ruff)" in calls
    assert "Type Checker (MyPy)" in calls
    assert "Unit Tests (Pytest)" in calls


def test_cmd_gate_full_run_all_pass_returns_ok(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-4: all steps pass -> EXIT_OK and the AST step appends a Passed result."""
    (tmp_path / "ok.py").write_text("import polars\n", encoding="utf-8")
    monkeypatch.setattr(cli, "run_command", lambda *_a, **_kw: (True, ""))
    args = cli._build_parser().parse_args(
        ["gate", "--target", str(tmp_path), "--github-summary"]
    )
    assert cli._cmd_gate(args) == cli.EXIT_OK


# ---------- M-7: prepush syntax-fail and bad-toml branches -----------------


def test_cmd_prepush_syntax_fail_returns_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = []\n', encoding="utf-8"
    )
    monkeypatch.setattr(compileall, "compile_dir", lambda *_a, **_kw: False)
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _FakeProc(returncode=0))
    args = cli._build_parser().parse_args(["prepush", "--target", str(tmp_path)])
    assert cli._cmd_prepush(args) == cli.EXIT_VIOLATION


def test_cmd_prepush_bad_toml_returns_config_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Malformed TOML -> tomllib.TOMLDecodeError -> EXIT_CONFIG.
    (tmp_path / "pyproject.toml").write_text("name = \n", encoding="utf-8")
    monkeypatch.setattr(compileall, "compile_dir", lambda *_a, **_kw: True)
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _FakeProc(returncode=0))
    args = cli._build_parser().parse_args(["prepush", "--target", str(tmp_path)])
    assert cli._cmd_prepush(args) == cli.EXIT_CONFIG


# ---------- I-4: psc replace write-failure path ----------------------------


def test_cmd_replace_write_oserror_returns_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I-4: an OSError during replace_code is caught, not raised as a traceback."""

    def boom(*_a: Any, **_kw: Any) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(cli, "replace_code", boom)
    args = cli._build_parser().parse_args(
        ["replace", "--file", "f.py", "--target", "target", "--new-code", "new.py"]
    )
    assert cli._cmd_replace(args) == cli.EXIT_VIOLATION


# ---------- M-2: heal --file unreadable path -------------------------------


def test_cmd_heal_unreadable_file_returns_config_error(
    tmp_path: Path,
) -> None:
    """M-2: a nonexistent --file is reported as EXIT_CONFIG, not a traceback."""
    args = cli._build_parser().parse_args(
        ["heal", "--file", str(tmp_path / "missing.log")]
    )
    assert cli._cmd_heal(args) == cli.EXIT_CONFIG


# ---------- I-2 / I-3: main() exit-code wrapper ----------------------------


def test_main_maps_tool_unavailable_to_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I-2: a missing launcher (ToolUnavailableError) -> EXIT_CONFIG."""

    def boom(_args: Any) -> int:
        raise ToolUnavailableError("uv not found")

    monkeypatch.setattr(cli, "_cmd_ast", boom)
    with pytest.raises(SystemExit) as exc:
        cli.main(["ast", "."])
    assert exc.value.code == cli.EXIT_CONFIG


def test_main_maps_unexpected_exception_to_internal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I-3: any unanticipated exception -> EXIT_INTERNAL (not a raw traceback)."""

    def boom(_args: Any) -> int:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(cli, "_cmd_ast", boom)
    with pytest.raises(SystemExit) as exc:
        cli.main(["ast", "."])
    assert exc.value.code == cli.EXIT_INTERNAL


def test_main_passes_through_normal_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normal handler return value is preserved by the wrapper."""
    monkeypatch.setattr(cli, "_cmd_ast", lambda _args: cli.EXIT_OK)
    with pytest.raises(SystemExit) as exc:
        cli.main(["ast", "."])
    assert exc.value.code == cli.EXIT_OK
