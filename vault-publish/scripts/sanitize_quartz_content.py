"""Unified Content Sanitizer for Quartz Digital Garden Deployments.

Performs all post-sync hygiene and sanitization in-place on quartz content/ markdown files:
  1. Frontmatter Fix: Quotes unquoted [[wikilinks]] and special characters in YAML frontmatter.
  2. Dataview Strip: Replaces ```dataview ... ``` blocks with a clean static callout.
  3. Dewikify Broken Links: Converts broken wikilinks to plain text so they don't 404.
  4. Strip Edit Logs: Removes '更新履歴:' frontmatter and AI-process callouts (Gemini編集, etc.).
  5. EOL Normalization: Enforces standard LF (\n) line endings across all files.

Usage:
  python sanitize_quartz_content.py <content_dir> [--dry-run]
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys
from typing import Final, Sequence

sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# 1. Frontmatter Fix
# ---------------------------------------------------------------------------
FM_RE: Final = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.DOTALL)
ARRAY_RE: Final = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*):\s*\[([^\[\]\n]*(?:\[\[[^\]]+\]\][^\[\]\n]*)*)\]\s*$",
    re.MULTILINE,
)
SCALAR_LINK_RE: Final = re.compile(
    r"^([^:\n]+):[ \t]+(.*?\[\[[^\]\n]+\]\][^\n]*)\s*$", re.MULTILINE
)


def _split_items(items_str: str) -> list[str]:
    parts = []
    depth = 0
    buf = []
    i = 0
    while i < len(items_str):
        c = items_str[i]
        if c == "[" and i + 1 < len(items_str) and items_str[i + 1] == "[":
            depth += 1
            buf.append("[[")
            i += 2
            continue
        if c == "]" and i + 1 < len(items_str) and items_str[i + 1] == "]":
            depth -= 1
            buf.append("]]")
            i += 2
            continue
        if c == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _fix_array_items(items_str: str) -> str:
    parts = _split_items(items_str)
    fixed = []
    for p in parts:
        if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
            fixed.append(p)
            continue
        needs_quote = (
            "[[" in p
            or p.startswith("#")
            or ":" in p
            or any(c in p for c in "{}&*?|<>=!%@`")
        )
        if needs_quote:
            escaped = p.replace('"', '\\"')
            fixed.append(f'"{escaped}"')
        else:
            fixed.append(p)
    return ", ".join(fixed)


def _fix_frontmatter_body(body: str) -> str:
    def repl_array(m: re.Match) -> str:
        key = m.group(1)
        raw_items = m.group(2)
        fixed_items = _fix_array_items(raw_items)
        return f"{key}: [{fixed_items}]"

    def repl_scalar(m: re.Match) -> str:
        key = m.group(1)
        val = m.group(2).strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            return m.group(0)
        escaped = val.replace('"', '\\"')
        return f'{key}: "{escaped}"'

    body = ARRAY_RE.sub(repl_array, body)
    body = SCALAR_LINK_RE.sub(repl_scalar, body)
    return body


def fix_frontmatter(content_dir: Path, dry_run: bool = False) -> int:
    modified = 0
    for p in content_dir.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        m = FM_RE.match(text)
        if not m:
            continue
        fm_body = m.group(1)
        new_fm_body = _fix_frontmatter_body(fm_body)
        if new_fm_body != fm_body:
            new_text = f"---\n{new_fm_body}\n---" + text[m.end() :]
            if not dry_run:
                p.write_text(new_text, encoding="utf-8")
            modified += 1
    return modified


# ---------------------------------------------------------------------------
# 2. Dataview Strip
# ---------------------------------------------------------------------------
DATAVIEW_RE: Final = re.compile(
    r"^[ \t]*```+dataview(?:js)?[ \t]*\r?\n.*?\r?\n[ \t]*```+[ \t]*$",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)
DATAVIEW_PLACEHOLDER: Final = "> ℹ️ この一覧は Obsidian 上で動的に表示されます（公開サイトでは省略）。"


def strip_dataview(content_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    files_modified = 0
    total_stripped = 0
    for p in content_dir.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        count = 0

        def repl(_m: re.Match) -> str:
            nonlocal count
            count += 1
            return DATAVIEW_PLACEHOLDER

        out = DATAVIEW_RE.sub(repl, text)
        if out != text:
            if not dry_run:
                p.write_text(out, encoding="utf-8")
            files_modified += 1
            total_stripped += count
    return files_modified, total_stripped


# ---------------------------------------------------------------------------
# 3. Dewikify Broken Wikilinks (with smart resolvers for shrine/archive patterns)
# ---------------------------------------------------------------------------
WIKILINK_RE: Final = re.compile(r"\[\[([^\[\]|]+?)(\|[^\]]+)?\]\]")
SH_RE: Final = re.compile(r"\[\[([^\[\]]+?\s*-\s*Shrine-heritager)(\|[^\]]+)?\]\]")
SOURCE_URL_RE: Final = re.compile(r"^source:\s*[\"']?(https?://[^\s\"']+)", re.MULTILINE)


def _build_archive_source_map() -> dict[str, str]:
    """Scan potential Web_Archives directories to map note basename -> source URL."""
    archive_map: dict[str, str] = {}
    candidate_paths = [
        Path(r"D:/Vault/awa/資料/Web_Archives"),
        Path(r"D:/Vault/資料/Web_Archives"),
    ]
    for archive_dir in candidate_paths:
        if not archive_dir.is_dir():
            continue
        for p in archive_dir.rglob("*.md"):
            try:
                head = p.read_text(encoding="utf-8")[:600]
            except OSError:
                continue
            m = SOURCE_URL_RE.search(head)
            if m:
                archive_map[p.stem] = m.group(1)
    return archive_map


def _slugify(name: str) -> str:
    s = name.replace(" ", "-")
    return s.strip("/")


def dewikify_broken(content_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    # Collect existing slugs and basenames
    existing = set()
    for p in content_dir.rglob("*.md"):
        rel = p.relative_to(content_dir).with_suffix("").as_posix()
        existing.add(rel)
        existing.add(rel.split("/")[-1])

    archive_source_url = _build_archive_source_map()

    def _resolves(link_name: str) -> bool:
        if not link_name:
            return False
        target = link_name.split("|", 1)[0].rstrip("\\").strip()
        target = target.split("#", 1)[0].strip()
        if not target:
            return True
        slug = _slugify(target)
        return slug in existing or target in existing

    files_modified = 0
    links_dewikified = 0

    from urllib.parse import quote

    for p in content_dir.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue

        count = 0
        out = text

        # 1. Shrine-heritager -> external search link
        def sh_repl(m: re.Match) -> str:
            nonlocal count
            full_name = m.group(1)
            alias = m.group(2)
            if _resolves(full_name):
                return m.group(0)
            display = alias[1:].strip() if alias else full_name.split("〈")[0].split("（")[0].strip()
            if display.endswith(" - Shrine-heritager"):
                display = display[: -len(" - Shrine-heritager")]
            search_url = f"https://shrineheritager.com/?s={quote(display)}"
            count += 1
            return f"[{display} (Shrine-heritager)]({search_url})"

        out = SH_RE.sub(sh_repl, out)

        # 2. General broken wikilinks -> archive URL or plain text
        def gen_repl(m: re.Match) -> str:
            nonlocal count
            target = m.group(1).strip()
            alias = m.group(2)
            display = alias[1:].strip() if alias else target

            if _resolves(target):
                return m.group(0)

            # Check if broken link points to a known Web_Archives note with source URL
            clean_target = target.split("|", 1)[0].rstrip("\\").strip().split("#", 1)[0].strip()
            basename = clean_target.split("/")[-1]
            if basename in archive_source_url:
                count += 1
                return f"[{display}]({archive_source_url[basename]})"

            count += 1
            return display

        out = WIKILINK_RE.sub(gen_repl, out)

        if out != text:
            if not dry_run:
                p.write_text(out, encoding="utf-8")
            files_modified += 1
            links_dewikified += count

    return files_modified, links_dewikified


# ---------------------------------------------------------------------------
# 4. Strip Edit Logs (AI-narrative sanitization)
# ---------------------------------------------------------------------------
FM_UPDATE_HISTORY_RE: Final = re.compile(r"^更新履歴:.*(?:\n(?:[ \t].*)?)*\n", re.MULTILINE)
PROCESS_VOCAB_RE: Final = re.compile(
    r"Gemini編集|一括編集|別AI|独立検証Agent|検証Agent|src_[\w]+\.md"
)
CALLOUT_BLOCK_RE: Final = re.compile(
    r"^\>\s*\[!(?:danger|warning)\].*?(?=^\>\s*\[!|\n\n(?!\>)|\Z)",
    re.MULTILINE | re.DOTALL,
)


def strip_edit_logs(content_dir: Path, dry_run: bool = False) -> tuple[int, int, int]:
    total_files = 0
    total_fm = 0
    total_danger = 0

    for p in content_dir.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue

        n_fm = len(FM_UPDATE_HISTORY_RE.findall(text))
        text_no_fm = FM_UPDATE_HISTORY_RE.sub("", text)

        n_danger = 0

        def _replace_danger(m: re.Match) -> str:
            nonlocal n_danger
            block = m.group(0)
            if PROCESS_VOCAB_RE.search(block):
                n_danger += 1
                return ""
            return block

        cleaned = CALLOUT_BLOCK_RE.sub(_replace_danger, text_no_fm)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        if n_fm or n_danger:
            if not dry_run:
                p.write_text(cleaned, encoding="utf-8")
            total_files += 1
            total_fm += n_fm
            total_danger += n_danger

    return total_files, total_fm, total_danger


# ---------------------------------------------------------------------------
# 5. EOL Normalization (LF)
# ---------------------------------------------------------------------------
def normalize_eol(content_dir: Path, dry_run: bool = False) -> int:
    fixed = 0
    for p in content_dir.rglob("*.md"):
        try:
            raw = p.read_bytes()
        except Exception:
            continue
        if b"\r" in raw:
            normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            if normalized != raw:
                if not dry_run:
                    p.write_bytes(normalized)
                fixed += 1
    return fixed


# ---------------------------------------------------------------------------
# Main Pipeline Runner
# ---------------------------------------------------------------------------
def sanitize_quartz_content(
    content_dir: Path,
    dry_run: bool = False,
    skip_frontmatter_fix: bool = False,
    skip_dataview_strip: bool = False,
    skip_dewikify: bool = False,
    skip_strip_logs: bool = False,
    skip_eol: bool = False,
) -> None:
    print("=" * 72)
    print("  [Quartz Content Sanitizer]")
    print(f"  Target:  {content_dir}")
    print(f"  Mode:    {'DRY RUN' if dry_run else 'APPLY'}")
    print("=" * 72)

    if not skip_frontmatter_fix:
        n_fm = fix_frontmatter(content_dir, dry_run)
        print(f"  ▶ Frontmatter fix:        {n_fm} file(s) updated")

    if not skip_dataview_strip:
        f_dv, n_dv = strip_dataview(content_dir, dry_run)
        print(f"  ▶ Strip dataview blocks:  {f_dv} file(s) ({n_dv} blocks stripped)")

    if not skip_dewikify:
        f_dw, n_dw = dewikify_broken(content_dir, dry_run)
        print(f"  ▶ Dewikify broken links:  {f_dw} file(s) ({n_dw} links converted)")

    if not skip_strip_logs:
        f_lg, n_h, n_c = strip_edit_logs(content_dir, dry_run)
        print(f"  ▶ Strip edit & AI logs:   {f_lg} file(s) ({n_h} history, {n_c} AI blocks stripped)")

    if not skip_eol:
        n_eol = normalize_eol(content_dir, dry_run)
        print(f"  ▶ Normalize line endings: {n_eol} file(s) normalized to LF")

    print("=" * 72)
    print("  Sanitization complete.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize Quartz content directory.")
    parser.add_argument("content_dir", help="Path to quartz content directory")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")
    parser.add_argument("--skip-frontmatter-fix", action="store_true")
    parser.add_argument("--skip-dataview-strip", action="store_true")
    parser.add_argument("--skip-dewikify", action="store_true")
    parser.add_argument("--skip-strip-logs", action="store_true")
    parser.add_argument("--skip-eol", action="store_true")
    args = parser.parse_args()

    target = Path(args.content_dir).resolve()
    if not target.exists() or not target.is_dir():
        print(f"ERROR: content directory does not exist: {target}", file=sys.stderr)
        return 1

    sanitize_quartz_content(
        target,
        dry_run=args.dry_run,
        skip_frontmatter_fix=args.skip_frontmatter_fix,
        skip_dataview_strip=args.skip_dataview_strip,
        skip_dewikify=args.skip_dewikify,
        skip_strip_logs=args.skip_strip_logs,
        skip_eol=args.skip_eol,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
