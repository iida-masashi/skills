"""Tests for the AST-policy baseline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from python_safe_coding.baseline import (
    BASELINE_VERSION,
    Fingerprint,
    filter_new,
    fingerprint_all,
    fingerprint_violation,
    read_baseline,
    write_baseline,
)

# ---------- fingerprint_violation -----------------------------------------


def test_fingerprint_pandas_import(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("import pandas as pd\n", encoding="utf-8")
    msg = f"{f}:1: ERROR: Use polars instead of pandas (Polars First)."
    fp = fingerprint_violation(msg, root=tmp_path)
    assert fp is not None
    assert fp.rule_id == "polars-first"
    assert fp.file == "x.py"
    assert fp.line_hash != ""


def test_fingerprint_unparseable_returns_none() -> None:
    assert fingerprint_violation("not a violation message") is None


def test_fingerprint_uses_relative_path_when_root_given(tmp_path: Path) -> None:
    sub = tmp_path / "pkg"
    sub.mkdir()
    f = sub / "x.py"
    f.write_text("import pandas\n", encoding="utf-8")
    msg = f"{f}:1: ERROR: Use polars instead of pandas (Polars First)."
    fp = fingerprint_violation(msg, root=tmp_path)
    assert fp is not None
    assert fp.file == "pkg/x.py"


def test_fingerprint_robust_to_line_drift(tmp_path: Path) -> None:
    """Adding lines above the violation must not change the fingerprint."""
    f = tmp_path / "x.py"
    f.write_text("import pandas as pd\n", encoding="utf-8")
    fp1 = fingerprint_violation(
        f"{f}:1: ERROR: Use polars instead of pandas (Polars First).",
        root=tmp_path,
    )
    f.write_text("# new comment\n# another\nimport pandas as pd\n", encoding="utf-8")
    fp2 = fingerprint_violation(
        f"{f}:3: ERROR: Use polars instead of pandas (Polars First).",
        root=tmp_path,
    )
    assert fp1 == fp2


def test_fingerprint_changes_with_actual_change(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("import pandas as pd\n", encoding="utf-8")
    fp1 = fingerprint_violation(
        f"{f}:1: ERROR: Use polars instead of pandas (Polars First).",
        root=tmp_path,
    )
    f.write_text("from pandas import DataFrame\n", encoding="utf-8")
    fp2 = fingerprint_violation(
        f"{f}:1: ERROR: Use polars instead of pandas (Polars First).",
        root=tmp_path,
    )
    assert fp1 != fp2


# ---------- read/write round-trip -----------------------------------------


def test_baseline_round_trip(tmp_path: Path) -> None:
    fps = [
        Fingerprint(file="a.py", rule_id="polars-first", line_hash="aaaa"),
        Fingerprint(file="b.py", rule_id="polars-first", line_hash="bbbb"),
    ]
    out = tmp_path / "baseline.json"
    write_baseline(out, fps)
    loaded = read_baseline(out)
    assert loaded == set(fps)


def test_baseline_missing_file_returns_empty_set(tmp_path: Path) -> None:
    assert read_baseline(tmp_path / "missing.json") == set()


def test_baseline_version_mismatch_raises(tmp_path: Path) -> None:
    out = tmp_path / "baseline.json"
    out.write_text(json.dumps({"version": 999, "fingerprints": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        read_baseline(out)


def test_baseline_payload_has_version(tmp_path: Path) -> None:
    out = tmp_path / "baseline.json"
    write_baseline(out, [])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["version"] == BASELINE_VERSION


@pytest.mark.parametrize("payload", ["[]", '"x"', "42", "null"])
def test_baseline_non_object_json_raises_valueerror(
    tmp_path: Path, payload: str
) -> None:
    """I-5: valid-but-non-object JSON must raise a *caught* ValueError, not crash
    callers with AttributeError on data.get(...)."""
    out = tmp_path / "baseline.json"
    out.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        read_baseline(out)


# ---------- M-5: io-error rule classification -----------------------------


def test_fingerprint_io_error_message(tmp_path: Path) -> None:
    """A 'Cannot read file' violation maps to rule_id 'io-error'."""
    f = tmp_path / "x.py"
    msg = f"{f}:0: ERROR: Cannot read file (boom)."
    fp = fingerprint_violation(msg, root=tmp_path)
    assert fp is not None
    assert fp.rule_id == "io-error"


# ---------- M-8: fingerprint_violation fallback branches ------------------


def test_fingerprint_keeps_path_when_outside_root(tmp_path: Path) -> None:
    """relative_to raises ValueError when the file is not under root; the
    original path is kept."""
    other = tmp_path / "elsewhere" / "x.py"
    root = tmp_path / "project"
    root.mkdir()
    msg = f"{other}:1: ERROR: Use polars instead of pandas (Polars First)."
    fp = fingerprint_violation(msg, root=root)
    assert fp is not None
    # Path not under root -> kept as-is (not made relative), stored posix-style.
    assert fp.file == other.as_posix()


def test_fingerprint_missing_file_has_empty_line_hash(tmp_path: Path) -> None:
    """When the referenced file does not exist, line_hash stays ''."""
    ghost = tmp_path / "ghost.py"  # never created
    msg = f"{ghost}:1: ERROR: Use polars instead of pandas (Polars First)."
    fp = fingerprint_violation(msg, root=tmp_path)
    assert fp is not None
    assert fp.line_hash == ""


# ---------- filter_new ----------------------------------------------------


def test_filter_new_suppresses_known(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("import pandas as pd\n", encoding="utf-8")
    msg = f"{f}:1: ERROR: Use polars instead of pandas (Polars First)."
    baseline = set(fingerprint_all([msg], root=tmp_path))
    new, stale = filter_new([msg], baseline, root=tmp_path)
    assert new == []
    assert stale == []


def test_filter_new_reports_unknown(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("import pandas as pd\n", encoding="utf-8")
    msg = f"{f}:1: ERROR: Use polars instead of pandas (Polars First)."
    new, stale = filter_new([msg], set(), root=tmp_path)
    assert new == [msg]
    assert stale == []


def test_filter_new_reports_stale_baseline_entries(tmp_path: Path) -> None:
    """Baseline entries not seen in current scan are listed as stale."""
    fp = Fingerprint(file="ghost.py", rule_id="polars-first", line_hash="dead")
    new, stale = filter_new([], {fp}, root=tmp_path)
    assert new == []
    assert stale == [fp]
