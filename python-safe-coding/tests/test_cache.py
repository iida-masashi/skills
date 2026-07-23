"""Tests for the per-file AST result cache."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from python_safe_coding.cache import CacheKey, load, make_key, store


def test_make_key_returns_none_for_missing(tmp_path: Path) -> None:
    assert make_key(tmp_path / "nope.py", checker_version=1) is None


def test_round_trip_hit(tmp_path: Path) -> None:
    src = tmp_path / "x.py"
    src.write_text("import polars\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    key = make_key(src, checker_version=1)
    assert key is not None
    store(cache_dir, key, ["err1", "err2"])
    assert load(cache_dir, key) == ["err1", "err2"]


def test_miss_when_mtime_changes(tmp_path: Path) -> None:
    src = tmp_path / "x.py"
    src.write_text("import polars\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"

    key_old = make_key(src, checker_version=1)
    assert key_old is not None
    store(cache_dir, key_old, [])

    # Bump mtime by writing again (sleep to ensure ns granularity registers).
    time.sleep(0.01)
    src.write_text("import polars\n# touched\n", encoding="utf-8")
    os.utime(src, None)

    key_new = make_key(src, checker_version=1)
    assert key_new is not None
    # New mtime/size -> cached entry is stale.
    assert load(cache_dir, key_new) is None


def test_miss_when_checker_version_bumps(tmp_path: Path) -> None:
    src = tmp_path / "x.py"
    src.write_text("import polars\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"

    key_v1 = make_key(src, checker_version=1)
    assert key_v1 is not None
    store(cache_dir, key_v1, ["v1 result"])

    key_v2 = make_key(src, checker_version=2)
    assert key_v2 is not None
    assert load(cache_dir, key_v2) is None  # version bump invalidates


def test_load_returns_none_for_missing_entry(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    key = CacheKey(path="/no/such/file.py", mtime_ns=0, size=0, checker_version=1)
    assert load(cache_dir, key) is None


def test_load_returns_none_for_corrupt_entry(tmp_path: Path) -> None:
    src = tmp_path / "x.py"
    src.write_text("import polars\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    key = make_key(src, checker_version=1)
    assert key is not None
    store(cache_dir, key, [])
    # Corrupt the cache file.
    entry = next(cache_dir.glob("*.json"))
    entry.write_text("not json", encoding="utf-8")
    assert load(cache_dir, key) is None


def test_store_swallows_io_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing write must not propagate; cache is best-effort."""
    src = tmp_path / "x.py"
    src.write_text("x\n", encoding="utf-8")
    key = make_key(src, checker_version=1)
    assert key is not None

    def fail_mkdir(*_a: object, **_kw: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    # No exception escapes.
    store(tmp_path / "cache", key, [])
