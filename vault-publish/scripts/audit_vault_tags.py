#!/usr/bin/env python3
"""Audit Vault frontmatter tags and normalize tag namespace variants.

Capabilities:
  1. Audit Tags: Scan YAML frontmatter tags across all markdown notes in a Vault.
     - Group tags by canonical 'leaf' name to detect namespace variants (e.g. `阿波忌部` vs `氏族/阿波忌部`).
     - Display top tags and tag variant clusters.
  2. Normalize Tags: Automatically rewrite minority tag variants to majority canonical forms based on frequency ratio (>= 5:1).

Usage:
    # Audit all tags in a Vault:
    python audit_vault_tags.py --vault D:/Vault/religion --audit

    # Audit with top tags:
    python audit_vault_tags.py --vault D:/Vault/religion --audit --top 30

    # Dry-run normalize tags:
    python audit_vault_tags.py --vault D:/Vault/awa --normalize

    # Actually apply normalization:
    python audit_vault_tags.py --vault D:/Vault/awa --normalize --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

FM_RE = re.compile(r"\A(---\r?\n)(.*?)(\r?\n---)", re.DOTALL)
TAGS_LINE_RE = re.compile(r"^(tags\s*:\s*)\[(.*?)\](\s*)$", re.MULTILINE)
TAGS_BLOCK_RE = re.compile(r"^(tags\s*:\s*\n)((?:[ \t]*-\s*.+\n?)+)", re.MULTILINE)
TAGS_ITEM_RE = re.compile(r"^([ \t]*-\s*)(.+?)(\s*)$", re.MULTILINE)


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1].strip()
    return s


def extract_tags_from_text(text: str) -> list[str]:
    m = FM_RE.match(text)
    if not m:
        return []
    body = m.group(2)
    tags = []
    inline = TAGS_LINE_RE.search(body)
    if inline:
        for part in inline.group(2).split(","):
            t = _strip_quotes(part)
            if t:
                tags.append(t)
    block = TAGS_BLOCK_RE.search(body)
    if block:
        for item_match in TAGS_ITEM_RE.finditer(block.group(2)):
            t = _strip_quotes(item_match.group(2))
            if t:
                tags.append(t)
    return tags


def leaf_name(tag: str) -> str:
    return tag.split("/")[-1].strip()


def audit_tags(
    vault_dir: Path,
    exclude_dirs: tuple[str, ...] = ("_work", ".obsidian", ".trash", ".git", ".venv"),
    top: int = 30,
) -> tuple[Counter[str], dict[str, list[tuple[str, int]]]]:
    all_tags: Counter[str] = Counter()
    tag_files: dict[str, list[Path]] = defaultdict(list)

    for md in vault_dir.rglob("*.md"):
        if any(part in exclude_dirs for part in md.parts):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        tags = extract_tags_from_text(text)
        for t in tags:
            all_tags[t] += 1
            tag_files[t].append(md)

    # Group by leaf
    by_leaf: dict[str, set[str]] = defaultdict(set)
    for t in all_tags:
        by_leaf[leaf_name(t)].add(t)

    variants: dict[str, list[tuple[str, int]]] = {}
    for leaf, forms in by_leaf.items():
        if len(forms) > 1:
            variants[leaf] = sorted([(f, all_tags[f]) for f in forms], key=lambda x: -x[1])

    print("=" * 72)
    print("  [Vault Tag Auditor]")
    print(f"  Vault: {vault_dir}")
    print("=" * 72)
    print(f"  Total unique tags: {len(all_tags):,}")
    print(f"  Total tag usages:  {sum(all_tags.values()):,}")
    print(f"  Variant clusters:  {len(variants)}")

    print(f"\n  Top {min(top, len(all_tags))} tags:")
    for tag, count in all_tags.most_common(top):
        print(f"    - [{count:>4}x] {tag}")

    if variants:
        print(f"\n  Detected {len(variants)} tag variant cluster(s):")
        for leaf, forms in sorted(variants.items(), key=lambda x: -sum(c for _, c in x[1])):
            summary = ", ".join(f"`{f}` ({c})" for f, c in forms)
            print(f"    - Leaf `{leaf}`: {summary}")

    print("=" * 72)
    return all_tags, variants


def normalize_tags(
    vault_dir: Path,
    exclude_dirs: tuple[str, ...] = ("_work", ".obsidian", ".trash", ".git", ".venv"),
    ratio_threshold: float = 5.0,
    apply_fixes: bool = False,
) -> tuple[int, int]:
    all_tags, variants = audit_tags(vault_dir, exclude_dirs)

    canonical_map: dict[str, str] = {}
    for leaf, forms in variants.items():
        if len(forms) < 2:
            continue
        top_form, top_cnt = forms[0]
        # Check if majority form is >= ratio_threshold * second form
        second_form, second_cnt = forms[1]
        if top_cnt >= ratio_threshold * second_cnt:
            # Map other forms to top form
            for f, cnt in forms[1:]:
                # skip bare leaf if it has significant usage (>= 3) and top is namespaced
                if f == leaf and cnt >= 3:
                    continue
                canonical_map[f] = top_form

    if not canonical_map:
        print("  No tag variants meet the threshold for automatic normalization.")
        return 0, 0

    print(f"\n  Normalization map ({len(canonical_map)} rules):")
    for src, dst in canonical_map.items():
        print(f"    `{src}` -> `{dst}`")

    if not apply_fixes:
        print("\n  [DRY RUN] No files modified. Use --apply to rewrite files.")

    files_modified = 0
    tags_rewritten = 0

    for md in vault_dir.rglob("*.md"):
        if any(part in exclude_dirs for part in md.parts):
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue

        m = FM_RE.match(text)
        if not m:
            continue

        prefix, body, suffix = m.group(1), m.group(2), m.group(3)
        rest_of_file = text[m.end():]
        modified = False
        file_count = 0

        # Replace in inline tags
        def inline_repl(im: re.Match) -> str:
            nonlocal modified, file_count
            tag_pre, raw_tags, tag_post = im.group(1), im.group(2), im.group(3)
            new_parts = []
            for part in raw_tags.split(","):
                t = _strip_quotes(part)
                if t in canonical_map:
                    new_parts.append(canonical_map[t])
                    modified = True
                    file_count += 1
                else:
                    new_parts.append(t)
            return f"{tag_pre}[{', '.join(new_parts)}]{tag_post}"

        new_body = TAGS_LINE_RE.sub(inline_repl, body)

        # Replace in block tags
        def block_repl(bm: re.Match) -> str:
            nonlocal modified, file_count
            block_pre, raw_block = bm.group(1), bm.group(2)
            lines = []
            for item_match in TAGS_ITEM_RE.finditer(raw_block):
                item_pre, val, item_post = item_match.group(1), item_match.group(2), item_match.group(3)
                t = _strip_quotes(val)
                if t in canonical_map:
                    lines.append(f"{item_pre}{canonical_map[t]}{item_post}")
                    modified = True
                    file_count += 1
                else:
                    lines.append(f"{item_pre}{val}{item_post}")
            return f"{block_pre}{''.join(lines)}"

        new_body = TAGS_BLOCK_RE.sub(block_repl, new_body)

        if modified:
            files_modified += 1
            tags_rewritten += file_count
            if apply_fixes:
                md.write_text(prefix + new_body + suffix + rest_of_file, encoding="utf-8")
            print(f"  {'Normalized' if apply_fixes else '[dry-run] Would normalize'} {file_count} tag(s) in: {md.name}")

    print(f"\n  Summary: {files_modified} file(s) modified, {tags_rewritten} tag(s) rewritten.")
    return files_modified, tags_rewritten


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and normalize YAML frontmatter tags in Vault")
    parser.add_argument("--vault", type=Path, required=True, help="Path to Vault root directory")
    parser.add_argument("--audit", action="store_true", help="Audit tags and display variant clusters")
    parser.add_argument("--normalize", action="store_true", help="Normalize minority tag variants to majority forms")
    parser.add_argument("--ratio", type=float, default=5.0, help="Majority-to-minority count ratio threshold (default: 5.0)")
    parser.add_argument("--top", type=int, default=30, help="Number of top tags to display")
    parser.add_argument("--apply", action="store_true", help="Apply normalization changes to files")
    args = parser.parse_args()

    if not args.vault.is_dir():
        print(f"ERROR: Vault directory not found: {args.vault}", file=sys.stderr)
        sys.exit(1)

    if args.normalize:
        normalize_tags(args.vault, ratio_threshold=args.ratio, apply_fixes=args.apply)
    else:
        audit_tags(args.vault, top=args.top)


if __name__ == "__main__":
    main()
