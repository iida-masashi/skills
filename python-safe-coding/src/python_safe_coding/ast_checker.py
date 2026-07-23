"""AST-based policy checker — Polars First.

Naive `datetime.now()` detection is delegated to Ruff's `DTZ005` (see ADR 0001).
This module enforces only the policies Ruff cannot express today:

- **Polars First**: `import pandas` / `from pandas import ...` is forbidden,
  even when used (Ruff's PD category warns about *usage patterns*, not the
  import itself).

Performance:
- Files are walked in parallel via `ThreadPoolExecutor` once the file count
  passes a small threshold. `ast.parse` is a C call that releases the GIL,
  so threads scale fine here without ProcessPool's spawn overhead.
- Optional per-file cache keyed by `(path, mtime, size, _CHECKER_VERSION)`.

Bump `_CHECKER_VERSION` when adding or modifying a rule — otherwise cached
results from before the change would be silently reused.
"""

from __future__ import annotations

import ast
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final

from python_safe_coding import cache as _cache

_CHECKER_VERSION: Final = 2

_SKIP_PARTS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        ".pytest_cache",
        "__pycache__",
        ".git",
        ".mypy_cache",
        ".ruff_cache",
        "build",
        "dist",
        ".eggs",
    }
)

# Parallelize once the file count is large enough to amortize pool spin-up.
_PARALLEL_THRESHOLD: Final = 16
_DEFAULT_MAX_WORKERS: Final = 8


def _is_pandas(module: str | None) -> bool:
    """True for `pandas` and any submodule (e.g. `pandas.testing`).

    Exact-equality would miss `import pandas.testing as tm` and
    `from pandas.api.types import ...`, silently bypassing the policy.
    """
    return module == "pandas" or (module or "").startswith("pandas.")


class PolicyVisitor(ast.NodeVisitor):
    """Records Polars-First import violations."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if _is_pandas(alias.name):
                self._add_error(
                    node.lineno, "Use polars instead of pandas (Polars First)."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # node.module is None for relative imports (`from . import x`).
        if _is_pandas(node.module):
            self._add_error(node.lineno, "Use polars instead of pandas (Polars First).")
        self.generic_visit(node)

    def _add_error(self, lineno: int, message: str) -> None:
        self.errors.append(f"{self.file_path}:{lineno}: ERROR: {message}")


def check_file(file_path: Path) -> list[str]:
    """Return policy violation messages for a single file."""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError:
        return [f"{file_path}:0: ERROR: Syntax error, could not parse AST."]
    except OSError as exc:
        return [f"{file_path}:0: ERROR: Cannot read file ({exc})."]

    visitor = PolicyVisitor(file_path)
    visitor.visit(tree)
    return visitor.errors


def _check_with_cache(file_path: Path, cache_dir: Path) -> list[str]:
    key = _cache.make_key(file_path, checker_version=_CHECKER_VERSION)
    if key is None:
        return check_file(file_path)
    cached = _cache.load(cache_dir, key)
    if cached is not None:
        return cached
    errors = check_file(file_path)
    _cache.store(cache_dir, key, errors)
    return errors


def _enumerate_files(
    target_path: Path,
    skip: frozenset[str],
) -> list[Path]:
    if target_path.is_file():
        return [target_path] if target_path.suffix == ".py" else []
    if target_path.is_dir():
        return [
            py
            for py in target_path.rglob("*.py")
            if not any(part in skip for part in py.parts)
        ]
    return []


def check_target(
    target_path: Path,
    skip_parts: frozenset[str] | None = None,
    *,
    cache_dir: Path | None = None,
) -> list[str]:
    """Walk a file or directory and return aggregated violations.

    Output is sorted by path so parallel scans produce stable diffs.

    Args:
        target_path: file or directory to scan.
        skip_parts: directory names to skip during walk.
        cache_dir: when set, cache per-file results under this directory.
            The cache survives across runs and invalidates automatically when
            the file's mtime/size or `_CHECKER_VERSION` changes.
    """
    skip = skip_parts or _SKIP_PARTS
    files = _enumerate_files(target_path, skip)
    if not files:
        return []

    runner = (
        (lambda p: _check_with_cache(p, cache_dir))
        if cache_dir is not None
        else check_file
    )

    workers = (
        min(os.cpu_count() or 1, _DEFAULT_MAX_WORKERS)
        if len(files) >= _PARALLEL_THRESHOLD
        else 1
    )

    if workers <= 1 or len(files) < 2:
        per_file_results = [runner(f) for f in files]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            per_file_results = list(pool.map(runner, files))

    # Sort by path for reproducible output regardless of thread scheduling.
    aggregated: list[tuple[Path, list[str]]] = list(
        zip(files, per_file_results, strict=True)
    )
    aggregated.sort(key=lambda item: str(item[0]))
    return [err for _, errs in aggregated for err in errs]
