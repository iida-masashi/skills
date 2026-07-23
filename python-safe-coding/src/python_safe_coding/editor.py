"""AST-based safe code replacement.

Replaces a function or class definition by name, preserving the rest of the file.
Decorators are included in the replaced span so that `@decorator`-style code
does not become an orphan when the underlying definition is rewritten.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DefNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def find_target_node(tree: ast.AST, target_name: str) -> DefNode | None:
    """Find the top-level function or class with the given name.

    Only top-level (module-scoped) definitions are considered, so methods on
    classes and nested helpers are not matched ambiguously. Use a dotted
    locator (e.g. `MyClass.method`) for nested targets.
    """
    if "." in target_name:
        return _find_nested(tree, target_name.split("."))
    if isinstance(tree, ast.Module):
        for node in tree.body:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == target_name
            ):
                return node
    return None


def _find_nested(tree: ast.AST, parts: list[str]) -> DefNode | None:
    if not isinstance(tree, ast.Module):
        return None
    current_body: list[ast.stmt] = list(tree.body)
    found: DefNode | None = None
    for part in parts:
        found = None
        for node in current_body:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == part
            ):
                found = node
                break
        if found is None:
            return None
        current_body = list(found.body)
    return found


def _span(node: DefNode) -> tuple[int, int]:
    """Return (start_line, end_line) inclusive of decorators, 1-based."""
    start = node.lineno
    if node.decorator_list:
        start = min(start, node.decorator_list[0].lineno)
    if node.end_lineno is None:  # pragma: no cover - end_lineno is set on 3.8+
        raise RuntimeError("AST node missing end_lineno; Python 3.8+ required.")
    return start, node.end_lineno


def replace_code(
    file_path: str | Path, target_name: str, new_code_path: str | Path
) -> None:
    """Replace `target_name` in `file_path` with the contents of `new_code_path`."""
    path_obj = Path(file_path)
    new_code_obj = Path(new_code_path)

    if not path_obj.exists():
        raise FileNotFoundError(f"File '{file_path}' not found.")
    if not new_code_obj.exists():
        raise FileNotFoundError(f"New code file '{new_code_path}' not found.")

    source_lines = path_obj.read_text(encoding="utf-8").splitlines(keepends=True)
    source_code = "".join(source_lines)

    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        raise SyntaxError(f"Cannot parse '{file_path}': {exc}") from exc

    target_node = find_target_node(tree, target_name)
    if target_node is None:
        raise ValueError(f"Target '{target_name}' not found in '{file_path}'.")

    start_line, end_line = _span(target_node)
    logger.info(
        "Replacing '%s' (lines %d-%d) in %s",
        target_name,
        start_line,
        end_line,
        path_obj,
    )

    new_code_lines = new_code_obj.read_text(encoding="utf-8").splitlines(keepends=True)
    final_lines = (
        source_lines[: start_line - 1] + new_code_lines + source_lines[end_line:]
    )
    final_source = "".join(final_lines)

    # Verify the result still parses before committing it to disk; a malformed
    # replacement must not leave the file in a broken state. (healer applies the
    # same safety net via full re-validation + revert.)
    try:
        ast.parse(final_source)
    except SyntaxError as exc:
        raise ValueError(
            f"Replacement of '{target_name}' produced invalid Python "
            f"in '{file_path}'; file left unchanged: {exc}"
        ) from exc

    path_obj.write_text(final_source, encoding="utf-8")

    logger.info("Replacement complete; run `psc gate` to verify.")
