"""Tests for the AST policy checker (Polars First only).

Naive `datetime.now()` detection is intentionally delegated to Ruff (DTZ005)
and is therefore NOT covered by this module any more.
"""

from __future__ import annotations

from pathlib import Path

from python_safe_coding.ast_checker import check_file, check_target


def _write(path: Path, src: str) -> Path:
    path.write_text(src, encoding="utf-8")
    return path


def test_pandas_import_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path / "a.py", "import pandas as pd\n")
    errors = check_file(f)
    assert len(errors) == 1
    assert "Use polars instead of pandas" in errors[0]


def test_pandas_submodule_import_is_flagged(tmp_path: Path) -> None:
    """I-1: `import pandas.testing` must not bypass the policy via exact-match."""
    f = _write(tmp_path / "a.py", "import pandas.testing as tm\n")
    errors = check_file(f)
    assert len(errors) == 1
    assert "Use polars instead of pandas" in errors[0]


def test_pandas_submodule_from_import_is_flagged(tmp_path: Path) -> None:
    """I-1: `from pandas.api.types import ...` must be flagged too."""
    f = _write(tmp_path / "a.py", "from pandas.api.types import is_numeric_dtype\n")
    errors = check_file(f)
    assert len(errors) == 1
    assert "Use polars instead of pandas" in errors[0]


def test_relative_import_is_not_flagged(tmp_path: Path) -> None:
    """Guard: `from . import x` has node.module=None and must not crash/flag."""
    f = _write(tmp_path / "a.py", "from . import sibling\n")
    assert check_file(f) == []


def test_lookalike_package_is_not_flagged(tmp_path: Path) -> None:
    """A package merely prefixed with 'pandas' (no dot) is a different package."""
    f = _write(tmp_path / "a.py", "import pandas_stubs\n")
    assert check_file(f) == []


def test_pandas_from_import_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path / "a.py", "from pandas import DataFrame\n")
    errors = check_file(f)
    assert len(errors) == 1


def test_polars_only_is_clean(tmp_path: Path) -> None:
    src = "import polars as pl\nx = pl.DataFrame()\n"
    assert check_file(_write(tmp_path / "a.py", src)) == []


def test_datetime_handling_delegated_to_ruff(tmp_path: Path) -> None:
    """AST checker no longer flags datetime.now(); Ruff DTZ005 owns that rule."""
    src = "from datetime import datetime\nx = datetime.now()\n"
    assert check_file(_write(tmp_path / "a.py", src)) == []


def test_check_target_walks_directory_and_skips_caches(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("import polars\n", encoding="utf-8")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "bad.py").write_text("import pandas\n", encoding="utf-8")
    errors = check_target(tmp_path)
    assert errors == []


def test_check_target_walks_directory_finds_violations(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("import polars\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "bad.py").write_text("import pandas\n", encoding="utf-8")
    errors = check_target(tmp_path)
    assert len(errors) == 1
    assert "bad.py" in errors[0]


def test_syntax_error_is_reported(tmp_path: Path) -> None:
    f = _write(tmp_path / "a.py", "def broken(:\n")
    errors = check_file(f)
    assert len(errors) == 1
    assert "Syntax error" in errors[0]


def test_unreadable_file_reports_io_error(tmp_path: Path) -> None:
    """M-5: the OSError branch (read_text on a directory) emits 'Cannot read file'."""
    a_dir = tmp_path / "looks_like.py"
    a_dir.mkdir()  # read_text on a directory raises OSError
    errors = check_file(a_dir)
    assert len(errors) == 1
    assert "Cannot read file" in errors[0]


# ---------- parallel + cache integration ----------------------------------


def test_check_target_output_is_sorted_by_path(tmp_path: Path) -> None:
    """Parallel walks must produce stable, path-sorted output."""
    # Create more files than the parallel threshold so the thread pool engages.
    for i in range(20):
        (tmp_path / f"f{i:02d}.py").write_text("import pandas\n", encoding="utf-8")
    errors = check_target(tmp_path)
    assert len(errors) == 20
    paths = [e.split(":", 1)[0] for e in errors]
    assert paths == sorted(paths)


def test_check_target_uses_cache(tmp_path: Path) -> None:
    src = tmp_path / "x.py"
    src.write_text("import polars\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"

    # First scan populates the cache.
    assert check_target(src, cache_dir=cache_dir) == []
    # The cache directory now has one entry per file scanned.
    assert any(cache_dir.glob("*.json"))
    # Second scan reads from the cache; result is identical.
    assert check_target(src, cache_dir=cache_dir) == []


def test_check_target_cache_invalidates_on_edit(tmp_path: Path) -> None:
    src = tmp_path / "x.py"
    src.write_text("import polars\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    assert check_target(src, cache_dir=cache_dir) == []

    # Edit -> the cache entry is stale and should be replaced with new errors.
    import os
    import time

    time.sleep(0.01)
    src.write_text("import pandas\n", encoding="utf-8")
    os.utime(src, None)
    errors = check_target(src, cache_dir=cache_dir)
    assert len(errors) == 1
    assert "Use polars instead of pandas" in errors[0]
