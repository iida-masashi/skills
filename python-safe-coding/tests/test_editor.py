"""Tests for AST-based safe code replacement."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from python_safe_coding.editor import find_target_node, replace_code


def test_find_top_level_function() -> None:
    tree = ast.parse("def f(): ...\nclass C:\n    def f(self): ...\n")
    node = find_target_node(tree, "f")
    assert isinstance(node, ast.FunctionDef)
    assert node.col_offset == 0  # confirms top-level binding


def test_find_class() -> None:
    tree = ast.parse("class C: ...\n")
    node = find_target_node(tree, "C")
    assert isinstance(node, ast.ClassDef)


def test_find_nested_method_with_dotted_name() -> None:
    tree = ast.parse("class C:\n    def m(self): ...\n")
    node = find_target_node(tree, "C.m")
    assert isinstance(node, ast.FunctionDef)
    assert node.name == "m"


def test_find_missing_returns_none() -> None:
    tree = ast.parse("x = 1\n")
    assert find_target_node(tree, "nope") is None


def test_replace_code_basic(tmp_path: Path) -> None:
    target = tmp_path / "t.py"
    target.write_text(
        "def old_func():\n    return 1\n\n"
        "def target_func():\n    return 2\n\n"
        "def another():\n    return 3\n",
        encoding="utf-8",
    )
    new = tmp_path / "new.py"
    new.write_text("def target_func():\n    return 42\n", encoding="utf-8")

    replace_code(target, "target_func", new)
    out = target.read_text(encoding="utf-8")
    assert "return 42" in out
    assert "return 2" not in out
    assert "def old_func():" in out
    assert "def another():" in out


def test_replace_code_preserves_decorators(tmp_path: Path) -> None:
    """Decorators belong to the def's span and must be replaced together."""
    target = tmp_path / "t.py"
    target.write_text(
        "@staticmethod\n"
        "@cache\n"
        "def target_func():\n    return 2\n\n"
        "def keep():\n    return 9\n",
        encoding="utf-8",
    )
    new = tmp_path / "new.py"
    new.write_text("def target_func():\n    return 42\n", encoding="utf-8")

    replace_code(target, "target_func", new)
    out = target.read_text(encoding="utf-8")
    assert "@staticmethod" not in out
    assert "@cache" not in out
    assert "return 42" in out
    assert "def keep():" in out


def test_replace_async_function(tmp_path: Path) -> None:
    target = tmp_path / "t.py"
    target.write_text(
        "async def target():\n    return await x()\n\ndef keep(): return 1\n",
        encoding="utf-8",
    )
    new = tmp_path / "new.py"
    new.write_text("async def target():\n    return 0\n", encoding="utf-8")
    replace_code(target, "target", new)
    out = target.read_text(encoding="utf-8")
    assert "return 0" in out
    assert "await x()" not in out


def test_replace_class(tmp_path: Path) -> None:
    target = tmp_path / "t.py"
    target.write_text(
        "@final\nclass Target:\n    x = 1\n\nclass Keep:\n    pass\n",
        encoding="utf-8",
    )
    new = tmp_path / "new.py"
    new.write_text("class Target:\n    x = 99\n", encoding="utf-8")
    replace_code(target, "Target", new)
    out = target.read_text(encoding="utf-8")
    assert "x = 99" in out
    assert "@final" not in out
    assert "class Keep:" in out


def test_replace_missing_raises(tmp_path: Path) -> None:
    target = tmp_path / "t.py"
    target.write_text("def a(): pass\n", encoding="utf-8")
    new = tmp_path / "new.py"
    new.write_text("def x(): pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not found"):
        replace_code(target, "nope", new)


def test_replace_file_missing_raises(tmp_path: Path) -> None:
    new = tmp_path / "new.py"
    new.write_text("def a(): pass\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        replace_code(tmp_path / "nope.py", "a", new)


def test_replace_new_code_missing_raises(tmp_path: Path) -> None:
    """M-6: a valid source but a missing new-code file raises FileNotFoundError."""
    target = tmp_path / "t.py"
    target.write_text("def a(): pass\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        replace_code(target, "a", tmp_path / "no_new.py")


def test_replace_unparseable_source_raises(tmp_path: Path) -> None:
    """M-6: a source file that does not parse raises SyntaxError('Cannot parse')."""
    target = tmp_path / "t.py"
    target.write_text("def f(:\n", encoding="utf-8")  # broken source
    new = tmp_path / "new.py"
    new.write_text("def f(): pass\n", encoding="utf-8")
    with pytest.raises(SyntaxError, match="Cannot parse"):
        replace_code(target, "f", new)


def test_replace_invalid_result_raises_and_leaves_file_unchanged(
    tmp_path: Path,
) -> None:
    """A replacement that breaks the file's syntax must abort before writing."""
    original = "def target():\n    return 1\n\ndef keep():\n    return 2\n"
    target = tmp_path / "t.py"
    target.write_text(original, encoding="utf-8")
    new = tmp_path / "new.py"
    # Unbalanced paren -> the resulting file does not parse.
    new.write_text("def target(:\n    return 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid Python"):
        replace_code(target, "target", new)

    # File must be byte-for-byte unchanged.
    assert target.read_text(encoding="utf-8") == original
