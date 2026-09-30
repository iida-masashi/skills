"""Mermaid Hygiene & Contrast Validator for Antigravity & Quartz.

Checks Mermaid diagrams in markdown files for:
  1. BLOCK_MISMATCH: Unclosed code blocks
  2. SUBGRAPH_MISMATCH: subgraph / end mismatch
  3. QUOTE_COLLISION: Unescaped quotes inside quoted labels
  4. INVALID_ARROW: Invalid flowchart arrows
  5. UNQUOTED_EDGE_LABEL: Unquoted bidirectional link labels (<--> |label|)
  6. HAZARDOUS_SUBGRAPH_ID: Punctuation in subgraph IDs causing Mermaid 11 lexer crashes
  7. DARK_FILL_WITHOUT_WHITE_TEXT: Dark background fill without white text (Contrast/Readability)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Final, Sequence


@dataclass(frozen=True)
class MermaidLintIssue:
    file: Path
    line_number: int
    severity: str  # ERROR | WARNING
    rule: str
    message: str
    snippet: str


def is_dark_color(color_str: str) -> bool:
    """YIQ輝度計算により、指定された色が暗色（輝度 < 130）か判定する"""
    c = color_str.strip().lower()
    if c.startswith("#"):
        h = c.lstrip("#")
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) == 6:
            try:
                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                brightness = (r * 299 + g * 587 + b * 114) / 1000
                return brightness < 130
            except ValueError:
                return False
    dark_names = {
        "black", "navy", "darkblue", "darkgreen", "maroon",
        "darkred", "purple", "midnightblue", "indigo", "teal"
    }
    return c in dark_names


def is_white_color(color_str: str | None) -> bool:
    """指定された文字色が白系（高コントラスト担保）か判定する"""
    if not color_str:
        return False
    c = color_str.strip().lower()
    return c in {"#ffffff", "#fff", "white", "#f8fafc", "#f1f5f9", "#e2e8f0"}


class MermaidValidator:
    def __init__(self, target_path: Path):
        self.target_path = target_path

    def lint_file(self, file_path: Path) -> list[MermaidLintIssue]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []

        lines = content.splitlines()
        issues: list[MermaidLintIssue] = []

        in_mermaid = False
        mermaid_start = 0
        block_lines: list[str] = []

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("```mermaid"):
                in_mermaid = True
                mermaid_start = idx
                block_lines = []
            elif stripped == "```" and in_mermaid:
                in_mermaid = False
                issues.extend(self._lint_block(file_path, block_lines, mermaid_start))
            elif in_mermaid:
                block_lines.append(line)

        if in_mermaid:
            issues.append(
                MermaidLintIssue(
                    file=file_path,
                    line_number=mermaid_start,
                    severity="ERROR",
                    rule="BLOCK_MISMATCH",
                    message="Mermaidブロックが閉じられていません (``` が欠落)",
                    snippet=lines[mermaid_start - 1][:80] if mermaid_start <= len(lines) else "",
                )
            )

        return issues

    def _lint_block(
        self, file: Path, lines: list[str], start_line: int
    ) -> list[MermaidLintIssue]:
        issues: list[MermaidLintIssue] = []

        # Rule 2: subgraph / end mismatch (Applicable to flowchart / graph)
        first_line = ""
        for line in lines:
            s = line.strip()
            if s and not s.startswith("%%"):
                first_line = s
                break

        is_sequence = first_line.startswith("sequenceDiagram")
        if not is_sequence:
            subgraph_count = 0
            end_count = 0
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("subgraph"):
                    subgraph_count += 1
                elif stripped == "end":
                    end_count += 1

            if subgraph_count != end_count:
                issues.append(
                    MermaidLintIssue(
                        file=file,
                        line_number=start_line,
                        severity="ERROR",
                        rule="SUBGRAPH_MISMATCH",
                        message=f"subgraph の開始数 ({subgraph_count}) と end の数 ({end_count}) が一致しません",
                        snippet=f"subgraphs: {subgraph_count}, ends: {end_count}",
                    )
                )

        for line_no, line in enumerate(lines, start=start_line + 1):
            stripped = line.strip()

            # Rule 3: Single quote collision inside style='...' attributes (e.g. L'Oreal)
            if "style='" in stripped:
                # Find content between style=' and the next '
                # If there are odd number of quotes before '>' or known collisions like L'Or
                if "L'Or" in stripped or "L'or" in stripped or re.search(r"style='[^']*'[^>]*'", stripped):
                    issues.append(
                        MermaidLintIssue(
                            file=file,
                            line_number=line_no,
                            severity="ERROR",
                            rule="QUOTE_COLLISION",
                            message="style='...' 属性内でアポストロフィ/シングルクォートが衝突しています (L’Oréal または ロレアル を使用してください)",
                            snippet=stripped[:80],
                        )
                    )

            # Rule 4: Invalid arrow operator (e.g. -->--> or --->>)
            if re.search(r"--+>--+>", stripped) or re.search(r"--->>>", stripped):
                issues.append(
                    MermaidLintIssue(
                        file=file,
                        line_number=line_no,
                        severity="ERROR",
                        rule="INVALID_ARROW",
                        message="不正な矢印演算子です",
                        snippet=stripped[:80],
                    )
                )

            # Rule 5: Unquoted bidirectional link with label: A <-->|label| B
            if re.search(r"<-->\s*\|[^\"|]+\|", stripped):
                issues.append(
                    MermaidLintIssue(
                        file=file,
                        line_number=line_no,
                        severity="ERROR",
                        rule="UNQUOTED_EDGE_LABEL",
                        message='双方向リンク <--> のラベルがダブルクォートで囲まれていません (例: <--> |"ラベル"|)',
                        snippet=stripped[:80],
                    )
                )

            # Rule 6: Hazardous characters in subgraph ID (Mermaid 11 lexer crash)
            if stripped.startswith("subgraph"):
                m_sg = re.match(r"^subgraph\s+([^\n\[]+)", stripped)
                if m_sg:
                    sg_id = m_sg.group(1).strip()
                    hazardous_chars = ["・", "/", "、", "。", ":", "：", "(", "（", ")", "）"]
                    found_hazards = [c for c in hazardous_chars if c in sg_id]
                    if found_hazards:
                        issues.append(
                            MermaidLintIssue(
                                file=file,
                                line_number=line_no,
                                severity="ERROR",
                                rule="HAZARDOUS_SUBGRAPH_ID",
                                message=f"subgraph の識別子(ID)にMermaid 11で構文エラーとなる記号 {found_hazards} が含まれています。IDから記号を除去し、表示名は subgraph ID[\"表示名\"] で指定してください",
                                snippet=stripped[:80],
                            )
                        )

        # Collect dark classes and styles in this block
        dark_classes: set[str] = set()
        dark_nodes: set[str] = set()

        for line in lines:
            s = line.strip()
            # Parse classDef
            if s.startswith("classDef "):
                m_cls = re.match(r"^classDef\s+([a-zA-Z0-9_\-]+)\s+(.*)", s)
                if m_cls:
                    cls_name, rest = m_cls.group(1), m_cls.group(2)
                    fill_m = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)", rest)
                    if fill_m and is_dark_color(fill_m.group(1)):
                        dark_classes.add(cls_name)
            # Parse style
            elif s.startswith("style "):
                m_style = re.match(r"^style\s+([a-zA-Z0-9_\-]+)\s+(.*)", s)
                if m_style:
                    node_id, rest = m_style.group(1), m_style.group(2)
                    fill_m = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)", rest)
                    if fill_m and is_dark_color(fill_m.group(1)):
                        dark_nodes.add(node_id)

        for line_no, line in enumerate(lines, start=start_line + 1):
            stripped = line.strip()

            # Rule 7: Dark background fill without explicit white text (Contrast/Readability issue)
            # In Mermaid 11 / Quartz HTML labels, classDef 'color' is overridden by base styles.
            # Nodes with dark fills MUST have <div style='... color:#ffffff;'> in their labels.
            node_m = re.finditer(r'([a-zA-Z0-9_\-]+)\s*\["([^"]+)"\](?::::([a-zA-Z0-9_\-]+))?', line)
            for nm in node_m:
                node_id = nm.group(1)
                label_text = nm.group(2)
                node_class = nm.group(3)

                is_node_dark = (node_class in dark_classes) or (node_id in dark_nodes)
                if is_node_dark:
                    has_explicit_white = bool(
                        re.search(r"color:\s*(#ffffff|#fff|white)", label_text, re.IGNORECASE)
                        or "<div style='color:#ffffff;'>" in label_text
                        or '<div style="color:#ffffff;">' in label_text
                    )
                    if not has_explicit_white:
                        issues.append(
                            MermaidLintIssue(
                                file=file,
                                line_number=line_no,
                                severity="ERROR",
                                rule="DARK_FILL_WITHOUT_WHITE_TEXT",
                                message=(
                                    f"ノード '{node_id}' に暗色背景クラス '{node_class or 'inline'}' が適用されていますが、"
                                    "ラベル内に明示的な白文字指定（<div style='color:#ffffff;'>）がありません。"
                                    "Mermaid 11/Quartz環境下ではclassDefのcolor属性が無視され黒文字になるため、"
                                    "GEMINI.md規律に従い明示的な白文字指定が必要です (--fix で自動修正可能)。"
                                ),
                                snippet=line.strip()[:80],
                            )
                        )

            # Rule 8: %% inside mermaid block (Quartz OFM deletes between %%...%%, breaking diagram)
            if "%%" in stripped:
                issues.append(
                    MermaidLintIssue(
                        file=file,
                        line_number=line_no,
                        severity="WARNING",
                        rule="MERMAID_COMMENT_HAZARD",
                        message=(
                            "Mermaidブロック内に '%%' コメントが存在します。Quartz (OFM) は %%...%% を "
                            "Obsidianコメントとしてブロックごと削除し、ダイアグラムが構文エラーで破損します。"
                        ),
                        snippet=stripped[:80],
                    )
                )

        return issues

    def fix_file(self, file_path: Path) -> int:
        """暗色背景ノードに <div style='color:#ffffff;'> を自動挿入して保存する"""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return 0

        lines = content.splitlines()
        new_lines: list[str] = []
        in_mermaid = False
        fixed_count = 0

        dark_classes: set[str] = set()
        dark_nodes: set[str] = set()

        # Pre-pass for classes in file
        for line in lines:
            s = line.strip()
            if s.startswith("```mermaid"):
                in_mermaid = True
            elif s == "```" and in_mermaid:
                in_mermaid = False
            elif in_mermaid:
                if s.startswith("classDef "):
                    m_cls = re.match(r"^classDef\s+([a-zA-Z0-9_\-]+)\s+(.*)", s)
                    if m_cls:
                        cls_name, rest = m_cls.group(1), m_cls.group(2)
                        fill_m = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)", rest)
                        if fill_m and is_dark_color(fill_m.group(1)):
                            dark_classes.add(cls_name)
                elif s.startswith("style "):
                    m_style = re.match(r"^style\s+([a-zA-Z0-9_\-]+)\s+(.*)", s)
                    if m_style:
                        node_id, rest = m_style.group(1), m_style.group(2)
                        fill_m = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)", rest)
                        if fill_m and is_dark_color(fill_m.group(1)):
                            dark_nodes.add(node_id)

        in_mermaid = False
        for line in lines:
            s = line.strip()
            if s.startswith("```mermaid"):
                in_mermaid = True
                new_lines.append(line)
                continue
            elif s == "```" and in_mermaid:
                in_mermaid = False
                new_lines.append(line)
                continue

            if in_mermaid:
                def replace_node(m: re.Match) -> str:
                    nonlocal fixed_count
                    node_id = m.group(1)
                    label = m.group(2)
                    cls_name = m.group(3)
                    is_dark = (cls_name in dark_classes) or (node_id in dark_nodes)

                    has_explicit_white = bool(
                        re.search(r"color:\s*(#ffffff|#fff|white)", label, re.IGNORECASE)
                        or "<div style='color:#ffffff;'>" in label
                        or '<div style="color:#ffffff;">' in label
                    )
                    if is_dark and not has_explicit_white:
                        fixed_count += 1
                        new_label = f"<div style='color:#ffffff;'>{label}</div>"
                        suffix = f":::{cls_name}" if cls_name else ""
                        return f'{node_id}["{new_label}"]{suffix}'
                    return m.group(0)

                mod_line = re.sub(
                    r'([a-zA-Z0-9_\-]+)\s*\["([^"]+)"\](?::::([a-zA-Z0-9_\-]+))?',
                    replace_node,
                    line,
                )
                new_lines.append(mod_line)
            else:
                new_lines.append(line)

        if fixed_count > 0:
            file_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return fixed_count

    def run(self, fix: bool = False) -> list[MermaidLintIssue]:
        issues: list[MermaidLintIssue] = []
        def _is_excluded(path: Path) -> bool:
            return any(
                part.startswith(".") or part in {".git", ".venv", "__pycache__", "_work", "node_modules"}
                for part in path.parts
            )

        md_files = [self.target_path] if self.target_path.is_file() else [
            p for p in self.target_path.rglob("*.md")
            if not _is_excluded(p)
        ]

        if fix:
            total_fixed = 0
            for p in md_files:
                cnt = self.fix_file(p)
                if cnt > 0:
                    total_fixed += cnt
                    print(f"  [FIXED] {p.name}: {cnt} node(s) wrapped with <div style='color:#ffffff;'>")
            if total_fixed > 0:
                print(f"\n  Total {total_fixed} node label(s) automatically fixed for high-contrast white text.\n")

        for p in md_files:
            issues.extend(self.lint_file(p))
        return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Mermaid diagrams for syntax and contrast issues.")
    parser.add_argument("target", nargs="?", default=".", help="Target markdown file or directory (default: current directory)")
    parser.add_argument("--strict", action="store_true", help="Fail on any issues including warnings")
    parser.add_argument("--fix", action="store_true", help="Automatically inject <div style='color:#ffffff;'> into dark background nodes")
    args = parser.parse_args()

    target_path = Path(args.target).resolve()
    print("=" * 72)
    print("  [Mermaid Hygiene & Contrast Validator]")
    print(f"  Target: {target_path}")
    if args.fix:
        print("  Mode:   AUTO-FIX")
    print("=" * 72)

    validator = MermaidValidator(target_path)
    issues = validator.run(fix=args.fix)

    errors = [i for i in issues if i.severity == "ERROR"]
    warnings = [i for i in issues if i.severity == "WARNING"]

    if not issues:
        print("\n  [PASS] No syntax or contrast issues found in Mermaid diagrams!\n")
        return 0

    print(f"\n  Found {len(issues)} issue(s) ({len(errors)} error(s), {len(warnings)} warning(s)):\n")
    for i in issues:
        rel = i.file.relative_to(target_path) if target_path.is_dir() else i.file.name
        print(f"  [{i.severity}] {rel}:{i.line_number} ({i.rule})")
        print(f"    Message: {i.message}")
        if i.snippet:
            print(f"    Snippet: {i.snippet}")
        print()

    if errors or (warnings and args.strict):
        print("  [FAIL] Validation failed. Please fix the above issues.\n")
        return 1

    print("  [WARN] Completed with warnings.\n")
    return 0


def validate_vault(vault_dir: Path, fail_on_error: bool = True) -> bool:
    """Validate all diagrams in a Vault. Suitable for importing in sync scripts."""
    print("=" * 72)
    print("  [Mermaid Validator] Checking all diagrams in Vault...")
    print("=" * 72)
    validator = MermaidValidator(vault_dir)
    issues = validator.run()
    errors = [i for i in issues if i.severity == "ERROR"]
    warnings = [i for i in issues if i.severity == "WARNING"]

    if not errors:
        count = len(list(p for p in vault_dir.rglob("*.md") if not any(x.startswith(".") or x in {"_work", "node_modules", "__pycache__"} for x in p.parts)))
        print(f"  [PASS] Checked {count} markdown files. 0 Mermaid syntax issues found!")
        if warnings:
            print(f"  [INFO] {len(warnings)} non-fatal warning(s) detected (e.g. %% comments).")
        print()
        return True

    print(f"\n  [FAIL] Found {len(errors)} Mermaid syntax/contrast error(s):")
    for i in errors:
        rel = i.file.relative_to(vault_dir)
        print(f"  [ERROR] {rel}:{i.line_number} ({i.rule})")
        print(f"    Message: {i.message}")
        if i.snippet:
            print(f"    Snippet: {i.snippet}")
        print()

    if fail_on_error:
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())

