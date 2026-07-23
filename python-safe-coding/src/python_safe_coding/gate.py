"""Quality-gate command runner and report writer.

Subprocess invocation uses argv lists (never `shell=True`) so that user-supplied
targets cannot be interpreted as shell metacharacters.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class ToolUnavailableError(RuntimeError):
    """The command launcher (e.g. `uv`) could not be started.

    Distinct from a nonzero exit: a missing launcher is an environment/config
    problem (exit 3), not a policy violation (exit 1). Note we can only detect a
    missing *launcher* here — a missing sub-tool (`uv run ruff` when ruff is
    absent) surfaces as a nonzero return code, indistinguishable from a real
    violation, so it is intentionally left as a violation.
    """


# ASCII status tags — emoji is avoided because some Windows terminals (cp932)
# break on Unicode glyphs.
_STATUS_OK = "[OK]"
_STATUS_FAIL = "[FAIL]"
_STATUS_ERROR = "[ERROR]"


@dataclass(frozen=True)
class StepResult:
    step: str
    status: str  # "Passed" | "Failed" | "Error"
    details: str


def _record(
    summary_data: list[StepResult] | None,
    step: str,
    status: str,
    details: str,
) -> None:
    if summary_data is not None:
        summary_data.append(StepResult(step=step, status=status, details=details))


def run_command(
    argv: list[str],
    description: str,
    summary_data: list[StepResult] | None = None,
    *,
    cwd: Path | None = None,
) -> tuple[bool, str]:
    """Run `argv` (no shell) and report success.

    Returns (success, combined_output).
    """
    logger.info("--- Running %s ---", description)
    try:
        result = subprocess.run(
            argv,
            check=False,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd) if cwd else None,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        err_msg = f"Error running {description}: {exc}"
        logger.exception(err_msg)
        _record(summary_data, description, "Error", err_msg)
        raise ToolUnavailableError(err_msg) from exc

    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    success = result.returncode == 0

    if success:
        logger.info("%s %s Passed", _STATUS_OK, description)
    else:
        logger.warning("%s %s Failed", _STATUS_FAIL, description)
        if result.stdout:
            logger.warning(result.stdout)
        if result.stderr:
            logger.warning(result.stderr)

    _record(
        summary_data,
        description,
        "Passed" if success else "Failed",
        combined.strip(),
    )
    return success, combined


def write_github_summary(summary_data: list[StepResult]) -> str:
    """Render a markdown summary; if GITHUB_STEP_SUMMARY is set, append to it."""
    lines = ["# Quality Gate Report", "", "| Step | Status |", "|---|---|"]
    for item in summary_data:
        tag = _STATUS_OK if item.status == "Passed" else _STATUS_FAIL
        lines.append(f"| {item.step} | {tag} {item.status} |")
    lines.append("")
    lines.append("## Details")
    lines.append("")
    for item in summary_data:
        if item.status != "Passed":
            lines.append(f"### {item.step}")
            lines.append("```text")
            lines.append(item.details[:2000])
            lines.append("```")
            lines.append("")
    md = "\n".join(lines)

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        try:
            with Path(summary_file).open("a", encoding="utf-8") as fh:
                fh.write(md)
        except OSError as exc:
            logger.warning("Failed to write GitHub summary: %s", exc)
    return md
