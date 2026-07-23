"""Tests for healer helpers — no network calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from python_safe_coding.healer import (
    _build_prompt,
    _generate_fix,
    make_diff,
    resolve_target,
    strip_codefence,
)

# --- Fakes for the Gemini SDK surface used by _generate_fix -----------------
#
# _generate_fix only touches `types_mod.GenerateContentConfig/ThinkingConfig/
# ThinkingLevel` (to build a config) and `client.models.generate_content(...)`.
# Both are injected as parameters, so we fake exactly that surface — no network.


class _FakeThinkingLevel:
    HIGH = "HIGH"
    MINIMAL = "MINIMAL"


class _FakeTypes:
    ThinkingLevel = _FakeThinkingLevel

    @staticmethod
    def ThinkingConfig(**_kw: Any) -> dict[str, Any]:
        return dict(_kw)

    @staticmethod
    def GenerateContentConfig(**_kw: Any) -> dict[str, Any]:
        return dict(_kw)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    """Records each call and replays a scripted sequence of outcomes.

    Each entry is either an exception instance to raise or a _FakeResponse.
    """

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = outcomes
        self.calls: list[str] = []

    def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        self.calls.append(model)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.models = _FakeModels(outcomes)


def test_strip_codefence_python() -> None:
    text = "preamble\n```python\nprint(1)\n```\ntrailing"
    assert strip_codefence(text) == "print(1)"


def test_strip_codefence_generic() -> None:
    text = "```\nprint(1)\n```"
    assert strip_codefence(text) == "print(1)"


def test_strip_codefence_no_fence() -> None:
    assert strip_codefence("plain code") == "plain code"


def test_resolve_target_existing(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("x = 1\n", encoding="utf-8")
    log = f"{f}:3: ERROR: oh no\n"
    assert resolve_target(log) == f


def test_resolve_target_missing(tmp_path: Path) -> None:
    log = f"{tmp_path / 'nope.py'}:3: ERROR: oh no\n"
    assert resolve_target(log) is None


def test_resolve_target_no_match() -> None:
    assert resolve_target("totally unrelated text") is None


def test_make_diff_renders_changes(tmp_path: Path) -> None:
    diff = make_diff(tmp_path / "a.py", "x = 1\n", "x = 2\n")
    assert "-x = 1" in diff
    assert "+x = 2" in diff


def test_make_diff_empty_when_unchanged(tmp_path: Path) -> None:
    src = "x = 1\n"
    assert make_diff(tmp_path / "a.py", src, src) == ""


def test_build_prompt_includes_error_and_source(tmp_path: Path) -> None:
    prompt = _build_prompt(tmp_path / "broken.py", "x = 1\n", "SyntaxError: bad")
    assert "SyntaxError: bad" in prompt
    assert "x = 1" in prompt
    assert "broken.py" in prompt
    # The prompt primes the model with an opening ```python fence.
    assert prompt.rstrip().endswith("```python")


# --- I-2: exception-handling contract in _generate_fix ----------------------


def test_generate_fix_returns_pro_result() -> None:
    """Happy path: the Pro model responds; no fallback occurs."""
    client = _FakeClient([_FakeResponse("```python\nx = 1\n```")])
    out = _generate_fix(client, "prompt", _FakeTypes)  # type: ignore[arg-type]
    assert out == "x = 1"
    assert client.models.calls == ["gemini-3.1-pro-preview"]


def test_generate_fix_falls_back_on_transient_error() -> None:
    """A generic (transient/API) error on Pro falls back to Flash."""
    client = _FakeClient(
        [RuntimeError("503 unavailable"), _FakeResponse("```python\ny = 2\n```")]
    )
    out = _generate_fix(client, "prompt", _FakeTypes)  # type: ignore[arg-type]
    assert out == "y = 2"
    # Pro tried first, then Flash.
    assert client.models.calls == ["gemini-3.1-pro-preview", "gemini-3.0-flash"]


@pytest.mark.parametrize("exc", [TypeError("bad arg"), AttributeError(), ValueError()])
def test_generate_fix_propagates_programming_errors(exc: Exception) -> None:
    """Programming-error types signal a bug in how we call the SDK and must
    propagate rather than be masked by a Flash retry (I-2)."""
    client = _FakeClient([exc])
    with pytest.raises(type(exc)):
        _generate_fix(client, "prompt", _FakeTypes)  # type: ignore[arg-type]
    # Fallback was NOT attempted.
    assert client.models.calls == ["gemini-3.1-pro-preview"]
