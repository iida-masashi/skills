"""Self-healing quality gate (Gemini-backed, optional).

The Gemini SDK is imported lazily so that `python-safe-coding` can be installed
without `[heal]` extras. Callers must invoke `self_heal_code(...)` only after
ensuring `google-genai` and `python-dotenv` are available.

Modes:
- **default**: write fix to disk, run Ruff + MyPy + pytest, optionally commit.
- **--dry-run**: produce a unified diff to stdout; do not modify the file.
- **--patch-only PATH**: write the unified diff to PATH; do not modify the file.
"""

from __future__ import annotations

import difflib
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type-check-only import
    from google.genai import Client as GenaiClient

logger = logging.getLogger("python_safe_coding.healer")

PRO_MODEL = "gemini-3.1-pro-preview"
FLASH_MODEL = "gemini-3.0-flash"
MAX_RETRIES = 3
# Capture both POSIX and Windows-style paths (e.g. `C:\foo\bar.py:42:`).
# NOTE: spaces are intentionally excluded. Widening the class to match spaced
# paths (e.g. `C:\Program Files\...`) regresses the common Ruff `--> <path>`
# format — re.search would capture a leading space or preceding words. Spaced
# absolute paths remain unmatched (graceful: healing aborts). See M-3 in
# docs/DEEP_AUDIT_2026-06-04.md.
_FILE_RE = re.compile(r"((?:[A-Za-z]:[\\/])?[A-Za-z0-9_./\\-]+\.py):\d+:")


class HealerDependencyError(RuntimeError):
    """Raised when [heal] extras (google-genai, python-dotenv) are missing."""


def _import_genai() -> tuple[Any, Any, Any]:
    """Import google-genai + dotenv lazily; raise a friendly error if missing."""
    try:
        from dotenv import load_dotenv
        from google import genai
        from google.genai import types
    except ImportError as exc:
        msg = (
            "Self-healer requires the [heal] extras. Install with:\n"
            "    uv pip install -e '.[heal]'\n"
            "or `pip install google-genai python-dotenv`."
        )
        raise HealerDependencyError(msg) from exc
    return genai, types, load_dotenv


def _generate_fix(client: GenaiClient, prompt: str, types_mod: Any) -> str:
    config_pro = types_mod.GenerateContentConfig(
        thinking_config=types_mod.ThinkingConfig(
            include_thoughts=False,
            thinking_level=types_mod.ThinkingLevel.HIGH,
        ),
        temperature=1.0,
    )
    try:
        logger.info("Reasoning with %s (HIGH thinking)...", PRO_MODEL)
        response = client.models.generate_content(
            model=PRO_MODEL,
            contents=prompt,
            config=config_pro,
        )
    except (TypeError, AttributeError, ValueError):
        # These signal a bug in how we call the SDK, not a transient API
        # failure — re-raise instead of masking it with a Flash retry.
        raise
    except Exception as exc:
        # SDK raises provider-specific errors; treat as transient and fall back.
        logger.warning("Pro model failed (%s); falling back to %s.", exc, FLASH_MODEL)
        config_flash = types_mod.GenerateContentConfig(
            thinking_config=types_mod.ThinkingConfig(
                include_thoughts=False,
                thinking_level=types_mod.ThinkingLevel.MINIMAL,
            ),
            temperature=1.0,
        )
        response = client.models.generate_content(
            model=FLASH_MODEL,
            contents=prompt,
            config=config_flash,
        )
    return strip_codefence((response.text or "").strip())


def strip_codefence(text: str) -> str:
    """Extract the Python source from a ```python``` codefence."""
    if "```python" in text:
        return text.split("```python", 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    return text


def _run(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd) if cwd else None,
    )


def _format_and_lint(file_path: Path) -> tuple[bool, str]:
    logger.info("Format + auto-fix pass on %s", file_path)
    _run(["uv", "run", "ruff", "format", str(file_path)])
    _run(["uv", "run", "ruff", "check", "--fix", str(file_path)])
    res = _run(["uv", "run", "ruff", "check", str(file_path)])
    if res.returncode == 0:
        return True, ""
    return False, (res.stdout or "") + "\n" + (res.stderr or "")


def _full_quality_bar(file_path: Path) -> tuple[bool, str]:
    res_mypy = _run(["uv", "run", "mypy", str(file_path), "--ignore-missing-imports"])
    if res_mypy.returncode != 0:
        return False, "MyPy:\n" + (res_mypy.stdout or "") + (res_mypy.stderr or "")
    res_pytest = _run(["uv", "run", "pytest", "-q"])
    if res_pytest.returncode != 0:
        return False, "Pytest:\n" + (res_pytest.stdout or "") + (
            res_pytest.stderr or ""
        )
    return True, ""


def _commit(file_path: Path) -> None:
    cwd = file_path.parent.absolute()
    add = _run(["git", "add", file_path.name], cwd=cwd)
    if add.returncode != 0:
        raise RuntimeError(f"git add failed: {add.stderr}")
    msg = f"bot(heal): auto-fixed errors in {file_path.name}"
    commit = _run(["git", "commit", "-m", msg], cwd=cwd)
    if commit.returncode != 0:
        raise RuntimeError(f"git commit failed: {commit.stderr}")
    logger.info("[OK] Auto-committed: %s", msg)


def _build_prompt(file_path: Path, source: str, error_log: str) -> str:
    return f"""<role>
You are a careful Python debugging engineer.
</role>

<data>
[Error log]
{error_log}

[Target file: {file_path.name}]
{source}
</data>

<task>
Repair the source so that the error log is resolved without breaking behavior.
Maintain type hints. Output ONLY the full corrected Python source inside a single
```python``` code fence.
</task>

```python
"""


def resolve_target(error_log: str) -> Path | None:
    """Pick the first existing .py file referenced in the error log."""
    match = _FILE_RE.search(error_log)
    if not match:
        return None
    candidate = Path(match.group(1))
    return candidate if candidate.exists() else None


def make_diff(file_path: Path, original: str, proposed: str) -> str:
    """Return a unified diff suitable for human review or `git apply`."""
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=f"a/{file_path.as_posix()}",
            tofile=f"b/{file_path.as_posix()}",
        )
    )


def _emit_preview(
    file_path: Path,
    original: str,
    proposed: str,
    *,
    patch_only: Path | None,
) -> bool:
    diff = make_diff(file_path, original, proposed)
    if not diff:
        logger.info("[OK] Model returned no changes.")
        return True
    if patch_only is not None:
        patch_only.write_text(diff, encoding="utf-8")
        logger.info(
            "[OK] Patch written to %s. Apply with 'git apply %s'.",
            patch_only,
            patch_only,
        )
    else:
        sys.stdout.write(diff)
        sys.stdout.flush()
    return True


def _healing_loop(
    client: GenaiClient,
    types_mod: Any,
    file_path: Path,
    original_code: str,
    initial_error: str,
    *,
    auto_commit: bool,
) -> bool:
    current_error = initial_error
    current_code = original_code

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("Healing attempt %d/%d on %s", attempt, MAX_RETRIES, file_path)
        try:
            new_code = _generate_fix(
                client,
                _build_prompt(file_path, current_code, current_error),
                types_mod,
            )
        except (TypeError, AttributeError, ValueError):
            raise
        except Exception:  # tolerate transient SDK/API failures
            logger.exception("Generation failed.")
            break
        if not new_code:
            logger.warning("Empty model response; aborting.")
            break

        file_path.write_text(new_code, encoding="utf-8")

        ruff_ok, ruff_err = _format_and_lint(file_path)
        if not ruff_ok:
            logger.warning("Ruff still failing after attempt %d.", attempt)
            current_error = ruff_err
            current_code = file_path.read_text(encoding="utf-8")
            continue

        full_ok, full_err = _full_quality_bar(file_path)
        if not full_ok:
            logger.warning("MyPy/pytest failing after attempt %d.", attempt)
            current_error = full_err
            current_code = file_path.read_text(encoding="utf-8")
            continue

        logger.info("[OK] Validation passed.")
        if auto_commit:
            try:
                _commit(file_path)
            except RuntimeError:
                logger.exception("Auto-commit failed.")
                return False
        return True

    logger.error("All healing attempts failed; reverting %s.", file_path)
    file_path.write_text(original_code, encoding="utf-8")
    return False


def self_heal_code(
    error_log: str,
    *,
    auto_commit: bool = False,
    dry_run: bool = False,
    patch_only: Path | None = None,
) -> bool:
    """Heal a target file referenced in `error_log`.

    Returns True on success (or when dry-run/patch-only completes).
    """
    genai, types_mod, load_dotenv = _import_genai()
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY missing; cannot self-heal.")
        return False
    client = genai.Client(api_key=api_key, vertexai=False)

    file_path = resolve_target(error_log)
    if file_path is None:
        logger.error("Could not identify a target .py file from the error log.")
        return False

    original_code = file_path.read_text(encoding="utf-8")

    if dry_run or patch_only is not None:
        try:
            new_code = _generate_fix(
                client,
                _build_prompt(file_path, original_code, error_log),
                types_mod,
            )
        except (TypeError, AttributeError, ValueError):
            raise
        except Exception:  # tolerate transient SDK/API failures
            logger.exception("Generation failed.")
            return False
        if not new_code:
            logger.warning("Empty model response.")
            return False
        return _emit_preview(file_path, original_code, new_code, patch_only=patch_only)

    return _healing_loop(
        client,
        types_mod,
        file_path,
        original_code,
        error_log,
        auto_commit=auto_commit,
    )
