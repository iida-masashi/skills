"""Per-file cache for AST checker results.

Cache key: (absolute_path, mtime_ns, size, checker_version).
- mtime+size mirrors what `make`/`ninja` use; cheaper than hashing every file.
- `checker_version` invalidates the entire cache when policy rules change so
  a new rule cannot silently inherit yesterday's "clean" verdict.

Storage: one JSON file per source path under `cache_dir`, keyed by a SHA-1 of
the absolute path. The directory is opaque; consumers should add it to
`.gitignore`.

Cache is OPT-IN. The standalone `check_target(...)` call still works without
any cache wiring — pass `cache_dir=None` (the default) to skip it entirely.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CACHE_FORMAT_VERSION: Final = 1


@dataclass(frozen=True)
class CacheKey:
    path: str
    mtime_ns: int
    size: int
    checker_version: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "path": self.path,
            "mtime_ns": self.mtime_ns,
            "size": self.size,
            "checker_version": self.checker_version,
            "format_version": CACHE_FORMAT_VERSION,
        }


def _entry_path(cache_dir: Path, source_path: Path) -> Path:
    digest = hashlib.sha1(
        str(source_path.resolve()).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    return cache_dir / f"{digest}.json"


def make_key(source_path: Path, *, checker_version: int) -> CacheKey | None:
    """Build a cache key from filesystem stats. Returns None if path unreadable."""
    try:
        st = source_path.stat()
    except OSError:
        return None
    return CacheKey(
        path=str(source_path.resolve()),
        mtime_ns=st.st_mtime_ns,
        size=st.st_size,
        checker_version=checker_version,
    )


def load(cache_dir: Path, key: CacheKey) -> list[str] | None:
    """Return cached errors for `key` if present and matching; else None."""
    entry = _entry_path(cache_dir, Path(key.path))
    if not entry.exists():
        return None
    try:
        data = json.loads(entry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("format_version") != CACHE_FORMAT_VERSION:
        return None
    cached_key = data.get("key", {})
    if (
        cached_key.get("path") != key.path
        or cached_key.get("mtime_ns") != key.mtime_ns
        or cached_key.get("size") != key.size
        or cached_key.get("checker_version") != key.checker_version
    ):
        return None
    errors = data.get("errors")
    if not isinstance(errors, list):
        return None
    return [str(e) for e in errors]


def store(cache_dir: Path, key: CacheKey, errors: list[str]) -> None:
    """Persist (key, errors) under `cache_dir`. Best-effort — silent on I/O error."""
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        entry = _entry_path(cache_dir, Path(key.path))
        payload = {
            "format_version": CACHE_FORMAT_VERSION,
            "key": key.to_dict(),
            "errors": errors,
        }
        entry.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        # Cache failures must never fail a check.
        return
