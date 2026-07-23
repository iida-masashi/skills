"""Tests for the gate command runner and summary writer."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from python_safe_coding.gate import (
    StepResult,
    ToolUnavailableError,
    run_command,
    write_github_summary,
)


def test_run_command_success() -> None:
    summary: list[StepResult] = []
    ok, out = run_command([sys.executable, "-c", "print('hi')"], "echo", summary)
    assert ok is True
    assert "hi" in out
    assert summary[0].status == "Passed"


def test_run_command_failure_records_step() -> None:
    summary: list[StepResult] = []
    ok, _ = run_command(
        [sys.executable, "-c", "raise SystemExit(2)"], "fail-step", summary
    )
    assert ok is False
    assert summary[0].status == "Failed"
    assert summary[0].step == "fail-step"


def test_run_command_no_shell_metacharacters_executed(tmp_path: Path) -> None:
    """Ensure argv-based invocation does not interpret shell metacharacters."""
    summary: list[StepResult] = []
    sentinel = tmp_path / "sentinel"
    # If shell=True were used, the `;` would let us run a second command.
    # With argv, the whole string is a single argument to `python -c`.
    ok, _ = run_command(
        [sys.executable, "-c", f"; open(r'{sentinel}','w').write('pwned')"],
        "shell-injection-guard",
        summary,
    )
    assert ok is False  # bad python syntax → exits non-zero
    assert not sentinel.exists()


def test_run_command_missing_executable_raises() -> None:
    """A missing launcher raises ToolUnavailableError (mapped to EXIT_CONFIG by
    main()), and still records an Error step for the report."""
    summary: list[StepResult] = []
    with pytest.raises(ToolUnavailableError):
        run_command(["definitely-not-a-real-binary-xyz"], "missing", summary)
    assert summary[0].status == "Error"


def test_write_github_summary_passed(tmp_path: Path) -> None:
    summary_file = tmp_path / "step_summary.md"
    data = [StepResult(step="Linting", status="Passed", details="All good")]
    with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
        result = write_github_summary(data)
    assert "[OK] Passed" in result
    assert "Linting" in result
    assert "[OK] Passed" in summary_file.read_text(encoding="utf-8")


def test_write_github_summary_failed(tmp_path: Path) -> None:
    summary_file = tmp_path / "step_summary.md"
    data = [StepResult(step="Testing", status="Failed", details="Trace here")]
    with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
        result = write_github_summary(data)
    assert "[FAIL] Failed" in result
    assert "Trace here" in result


def test_write_github_summary_no_env_var() -> None:
    data = [StepResult(step="X", status="Passed", details="")]
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
    with patch.dict(os.environ, env, clear=True):
        result = write_github_summary(data)
    assert "[OK] Passed" in result
