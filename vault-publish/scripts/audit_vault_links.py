#!/usr/bin/env python3
"""Audit Vault wikilinks, detect red-links (unresolved wikilinks), and fix font-variant bugs.

Capabilities:
  1. Check Red-links: Scan markdown files for [[wikilink]]s whose target note does not exist in the Vault.
  2. Find Glyph-Variant Bugs: Detect red-links whose target matches an existing note via CJK glyph folding (e.g. 賣↔売, 彌↔弥, 嶋↔島, 髙↔高).
  3. Fix Glyph-Variant Bugs: Safely rewrite ambiguous-free variant red-links in-place to target existing canonical notes.

Usage:
    # Check all red-links in a Vault:
    python audit_vault_links.py --vault D:/Vault/religion --check-redlinks --top 30

    # Detect font-variant bugs:
    python audit_vault_links.py --vault D:/Vault/awa --find-variants

    # Fix font-variant bugs (dry run by default):
    python audit_vault_links.py --vault D:/Vault/awa --fix-variants

    # Actually apply fixes:
    python audit_vault_links.py --vault D:/Vault/awa --fix-variants --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")

# Known CJK glyph variants that Obsidian treats as DISTINCT.
# Folded to a single representative character.
VARIANT_FOLD: dict[str, str] = {
    "賣": "売",  # 八倉比賣 vs 八倉比売
    "彌": "弥",
    "祢": "弥",  # 多祁御奈刀祢 vs 多祁御奈刀弥
    "禰": "弥",
    "鍾": "鐘",  # 鍾乳洞 vs 鐘乳洞
    "鐘": "鐘",
    "藪": "薮",
    "嶋": "島",
    "嶌": "島",
    "凜": "凛",
    "檜": "桧",
    "假": "仮",
    "髙": "高",
    "﨑": "崎",
    "齋": "斎",
    "齊": "斉",
    "邊": "辺",
    "邉": "辺",
    "嶽": "岳",
    "栁": "柳",
    "淨": "浄",
    "廣": "広",
    "惠": "恵",
    "眞": "真",
    "國": "国",
    "佛": "仏",
    "靈": "霊",
    "禮": "礼",
    "壽": "寿",
    "萬": "万",
    "寶": "宝",
    "龍": "竜",
}


def norm_nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip().lower()


def fold_variant(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = "".join(VARIANT_FOLD.get(ch, ch) for ch in s)
    return s.strip().lower()


def link_basename(inner: str) -> str | None:
    """Extract canonical target basename from wikilink content.

    Handles embeds, aliases, anchors, blocks, and subpaths:
      [[X]] -> X
      [[X|alias]] -> X
      [[X#heading]] -> X
      [[path/to/X]] -> X
      [[#heading]] -> None (in-page)
    """
    target = inner.split("|", 1)[0].rstrip("\\").strip()
    target = target.split("#", 1)[0].strip()
    target = target.split("^", 1)[0].strip()
    if not target:
        return None
    return target.split("/")[-1].strip()


def build_vault_universe(vault_dir: Path, exclude_dirs: tuple[str, ...] = ("_work", ".obsidian", ".trash", ".git", ".venv")) -> tuple[set[str], set[str], dict[str, list[str]]]:
    """Scan vault and build indices:
    - md_stems: set of normalized markdown stems (e.g., '八倉比売')
    - all_basenames: set of all normalized filenames
    - stem_to_actual: folded_stem -> list of actual stem names
    """
    md_stems: set[str] = set()
    all_basenames: set[str] = set()
    stem_to_actual: dict[str, list[str]] = defaultdict(list)

    for p in vault_dir.rglob("*"):
        if not p.is_file():
            continue
        if any(part in exclude_dirs for part in p.parts):
            continue
        name = p.name
        norm_name = norm_nfc(name)
        all_basenames.add(norm_name)
        if name.lower().endswith(".md"):
            stem = name[:-3]
            norm_stem = norm_nfc(stem)
            md_stems.add(norm_stem)
            actual_nfc = unicodedata.normalize("NFC", stem)
            stem_to_actual[fold_variant(stem)].append(actual_nfc)

    return md_stems, all_basenames, stem_to_actual


def link_resolves(base: str, md_stems: set[str], all_basenames: set[str]) -> bool:
    nb = norm_nfc(base)
    return nb in md_stems or nb in all_basenames


def collect_redlinks(
    vault_dir: Path,
    md_stems: set[str],
    all_basenames: set[str],
    exclude_dirs: tuple[str, ...] = ("_work", ".obsidian", ".trash", ".git", ".venv"),
) -> dict[str, dict]:
    """Scan markdown files and return red-links:
    {target_nfc: {"count": int, "files": set[Path]}}
    """
    red: dict[str, dict] = {}
    for p in vault_dir.rglob("*.md"):
        if any(part in exclude_dirs for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue

        for m in WIKILINK_RE.finditer(text):
            base = link_basename(m.group(1))
            if base is None or link_resolves(base, md_stems, all_basenames):
                continue
            key = unicodedata.normalize("NFC", base)
            entry = red.setdefault(key, {"count": 0, "files": set()})
            entry["count"] += 1
            entry["files"].add(p)
    return red


def find_variant_bugs(
    red: dict[str, dict],
    stem_to_actual: dict[str, list[str]],
) -> list[dict]:
    """Correlate red-links with existing notes via CJK glyph folding."""
    bugs = []
    for base, entry in red.items():
        candidates = stem_to_actual.get(fold_variant(base), [])
        # Exclude exact match (not a variant)
        candidates = [c for c in candidates if c != base]
        unique_cands = sorted(set(candidates))
        if unique_cands:
            bugs.append({
                "count": entry["count"],
                "red": base,
                "candidates": unique_cands,
                "correct": unique_cands[0] if len(unique_cands) == 1 else None,
                "ambiguous": len(unique_cands) > 1,
                "files": sorted(str(p) for p in entry["files"]),
            })
    bugs.sort(key=lambda b: -b["count"])
    return bugs


def fix_variant_bugs(
    bugs: list[dict],
    apply_fixes: bool = False,
) -> tuple[int, int]:
    """Rewrite ambiguous-free variant red-links in target files."""
    unambiguous_bugs = [b for b in bugs if not b["ambiguous"] and b["correct"]]
    if not unambiguous_bugs:
        print("  No unambiguous variant bugs to fix.")
        return 0, 0

    fixmap = {unicodedata.normalize("NFC", b["red"]): unicodedata.normalize("NFC", b["correct"]) for b in unambiguous_bugs}
    target_files = sorted({f for b in unambiguous_bugs for f in b["files"]})

    files_modified = 0
    links_rewritten = 0

    print(f"\n  Ready to fix {len(fixmap)} distinct variant target(s) across {len(target_files)} file(s).")
    if not apply_fixes:
        print("  [DRY RUN] No files will be modified. Use --apply to write changes.\n")

    for file_str in target_files:
        p = Path(file_str)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            print(f"  WARN: could not read {p}")
            continue

        count = 0

        def repl(m: re.Match) -> str:
            nonlocal count
            full_match = m.group(0)
            inner = m.group(1)
            target = inner.split("|", 1)[0].rstrip("\\").strip()
            anchor_part = ""
            if "#" in target:
                target, anchor_part = target.split("#", 1)
                anchor_part = "#" + anchor_part
            elif "^" in target:
                target, anchor_part = target.split("^", 1)
                anchor_part = "^" + anchor_part

            target_base = target.split("/")[-1].strip()
            target_nfc = unicodedata.normalize("NFC", target_base)

            if target_nfc in fixmap:
                correct_base = fixmap[target_nfc]
                # preserve path prefix if present
                if "/" in target:
                    prefix = target.rsplit("/", 1)[0] + "/"
                    new_target = prefix + correct_base + anchor_part
                else:
                    new_target = correct_base + anchor_part

                count += 1
                if "|" in inner:
                    alias = inner.split("|", 1)[1]
                    return f"[[{new_target}|{alias}]]" if not full_match.startswith("!") else f"![[{new_target}|{alias}]]"
                else:
                    return f"[[{new_target}]]" if not full_match.startswith("!") else f"![[{new_target}]]"
            return full_match

        new_text = WIKILINK_RE.sub(repl, text)
        if new_text != text:
            files_modified += 1
            links_rewritten += count
            if apply_fixes:
                p.write_text(new_text, encoding="utf-8")
            print(f"  {'Fixed' if apply_fixes else '[dry-run] Would fix'} {count} link(s) in: {p.name}")

    print(f"\n  Summary: {files_modified} file(s) affected, {links_rewritten} link(s) rewritten.")
    return files_modified, links_rewritten


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Vault wikilinks, detect red-links, and fix font-variant bugs")
    parser.add_argument("--vault", type=Path, required=True, help="Path to Vault root directory")
    parser.add_argument("--check-redlinks", action="store_true", help="Report unresolved wikilinks (red-links)")
    parser.add_argument("--find-variants", action="store_true", help="Detect CJK glyph-variant bugs among red-links")
    parser.add_argument("--fix-variants", action="store_true", help="Fix glyph-variant bugs (dry-run by default)")
    parser.add_argument("--apply", action="store_true", help="Apply fixes to files (with --fix-variants)")
    parser.add_argument("--top", type=int, default=30, help="Number of top red-links to display")
    parser.add_argument("--target", type=str, default=None, help="Inspect specific wikilink target")
    parser.add_argument("--json-out", type=Path, default=None, help="Save variant bugs to JSON file")
    args = parser.parse_args()

    if not args.vault.is_dir():
        print(f"ERROR: Vault directory not found: {args.vault}", file=sys.stderr)
        sys.exit(1)

    print("=" * 72)
    print("  [Vault Wikilink & Variant Auditor]")
    print(f"  Vault: {args.vault}")
    print("=" * 72)

    md_stems, all_basenames, stem_to_actual = build_vault_universe(args.vault)
    print(f"  Indexed {len(md_stems):,} markdown notes and {len(all_basenames):,} total files.")

    red = collect_redlinks(args.vault, md_stems, all_basenames)
    total_red_occ = sum(e["count"] for e in red.values())
    print(f"  Found {len(red):,} distinct red-link targets ({total_red_occ:,} total occurrences).")

    if args.target:
        norm_t = norm_nfc(args.target)
        if norm_t in red:
            info = red[norm_t]
            print(f"\n  Target: [[{args.target}]] -> {info['count']} occurrence(s):")
            for f in info["files"]:
                print(f"    - {f}")
        else:
            print(f"\n  Target [[{args.target}]] is NOT a red-link (or not found).")

    if args.check_redlinks:
        print(f"\n  Top {min(args.top, len(red))} red-links:")
        sorted_red = sorted(red.items(), key=lambda item: -item[1]["count"])
        for tgt, info in sorted_red[: args.top]:
            print(f"    - [{info['count']:>3}x] [[{tgt}]] ({len(info['files'])} files)")

    if args.find_variants or args.fix_variants:
        bugs = find_variant_bugs(red, stem_to_actual)
        print(f"\n  Found {len(bugs)} glyph-variant bug(s) that resolve to existing notes:")
        for b in bugs:
            cand_str = ", ".join(f"[[{c}]]" for c in b["candidates"])
            ambig = " [AMBIGUOUS!]" if b["ambiguous"] else ""
            print(f"    - [{b['count']:>2}x] [[{b['red']}]] -> {cand_str}{ambig}")

        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(bugs, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n  Saved variant bugs to: {args.json_out}")

        if args.fix_variants:
            fix_variant_bugs(bugs, apply_fixes=args.apply)

    print("=" * 72)


if __name__ == "__main__":
    main()
