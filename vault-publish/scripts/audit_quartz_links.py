#!/usr/bin/env python3
"""Audit internal links in Quartz public/ output directory.

Scans all emitted .html files, extracts internal links (<a class="internal..."),
resolves relative paths to slugs, and reports broken links (404 targets).

Usage:
    python audit_quartz_links.py --public-dir C:/Users/iidam/quartz-religion/public
    python audit_quartz_links.py --public-dir C:/Users/iidam/quartz/public --report-file report.md
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

sys.stdout.reconfigure(encoding="utf-8")

ANCHOR_RE = re.compile(r"<a\s+([^>]+)>", re.IGNORECASE)
HREF_ATTR_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)
CLASS_ATTR_RE = re.compile(r'class="(internal[^"]*)"', re.IGNORECASE)


def resolve(page_slug: str, href: str) -> str | None:
    """Resolve relative href to an absolute slug under public/. Same logic as a browser."""
    if href.startswith(("http://", "https://", "mailto:", "#", "javascript:")):
        return None
    href_clean = href.split("#", 1)[0].split("?", 1)[0]
    if not href_clean:
        return None
    href_decoded = unquote(href_clean)
    page_parts = page_slug.split("/")
    page_dir = page_parts[:-1] if len(page_parts) > 1 else []

    if href_decoded.startswith("/"):
        href_decoded = href_decoded.lstrip("/")
        target_parts = href_decoded.split("/")
    else:
        target_parts = page_dir + href_decoded.split("/")

    normalized = []
    for part in target_parts:
        if part in ("", "."):
            continue
        if part == "..":
            if normalized:
                normalized.pop()
            continue
        normalized.append(part)
    return "/".join(normalized) or None


def audit_quartz_links(
    public_dir: Path,
    report_file: Path | None = None,
    top: int = 30,
) -> tuple[int, int, int]:
    """Audit links in public_dir.

    Returns:
        (total_slugs, broken_targets_count, total_broken_occurrences)
    """
    if not public_dir.is_dir():
        print(f"ERROR: public directory does not exist: {public_dir}", file=sys.stderr)
        return 0, 0, 0

    print("=" * 72)
    print("  [Quartz Internal Link Auditor]")
    print(f"  Target: {public_dir}")
    print("=" * 72)

    existing = set()
    for p in public_dir.rglob("*.html"):
        rel = p.relative_to(public_dir).as_posix()
        if rel.endswith("/index.html"):
            rel = rel[:-11]
        elif rel.endswith(".html"):
            rel = rel[:-5]
        existing.add(rel)

    print(f"  Scanned {len(existing):,} HTML slugs.")

    broken_targets: Counter[str] = Counter()
    broken_by_page: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for p in public_dir.rglob("*.html"):
        rel = p.relative_to(public_dir).as_posix()
        if rel.endswith("/index.html"):
            page_slug = rel[:-11]
        elif rel.endswith(".html"):
            page_slug = rel[:-5]
        else:
            continue

        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for m in ANCHOR_RE.finditer(text):
            attrs = m.group(1)
            cls_m = CLASS_ATTR_RE.search(attrs)
            if not cls_m or "internal" not in cls_m.group(1):
                continue
            href_m = HREF_ATTR_RE.search(attrs)
            if not href_m:
                continue
            href = href_m.group(1)
            target = resolve(page_slug, href)
            if target is None:
                continue
            if target in existing:
                continue
            broken_targets[target] += 1
            broken_by_page[page_slug].append((href, target))

    total_broken_occ = sum(broken_targets.values())
    print(f"  Broken targets (unique): {len(broken_targets):,}")
    print(f"  Total broken occurrences: {total_broken_occ:,}")
    print(f"  Pages affected:           {len(broken_by_page):,}")

    if broken_targets:
        print(f"\n  Top {min(top, len(broken_targets))} broken link targets:")
        for tgt, count in broken_targets.most_common(top):
            print(f"    - [{count:>3}x] {tgt}")
    else:
        print("\n  [PASS] All internal links resolve cleanly! 0 broken links found.")

    if report_file:
        lines = [
            "---",
            "title: Quartz リンク切れ監査レポート",
            f"date: {Path.cwd()}",
            "---",
            "",
            "# Quartz 内部リンク監査レポート",
            "",
            f"- 走査対象: `{public_dir}`",
            f"- 既存HTMLスラグ数: **{len(existing):,}**",
            f"- リンク切れターゲット(ユニーク): **{len(broken_targets):,}**",
            f"- リンク切れ総出現回数: **{total_broken_occ:,}**",
            f"- 影響を受けるページ数: **{len(broken_by_page):,}**",
            "",
            "## 上位リンク切れターゲット",
            "",
            "| 出現回数 | リンク切れターゲット |",
            "| ---: | --- |",
        ]
        for tgt, count in broken_targets.most_common(100):
            lines.append(f"| {count} | `{tgt}` |")
        lines.append("")
        lines.append("## 影響を受けるページ Top 30")
        lines.append("")
        lines.append("| ページ | 壊れたリンク数 |")
        lines.append("| --- | ---: |")
        for page, links in sorted(broken_by_page.items(), key=lambda x: -len(x[1]))[:30]:
            lines.append(f"| `{page}` | {len(links)} |")
        lines.append("")

        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n  Report saved to: {report_file}")

    print("=" * 72)
    return len(existing), len(broken_targets), total_broken_occ


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit internal links in Quartz public/ output")
    parser.add_argument(
        "--public-dir",
        type=Path,
        default=Path(os.environ.get("QUARTZ_PUBLIC_DIR", "public")),
        help="Path to Quartz public/ output directory",
    )
    parser.add_argument("--report-file", type=Path, default=None, help="Save markdown report to file")
    parser.add_argument("--top", type=int, default=30, help="Number of top broken targets to display")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit code 1 if broken links found")
    args = parser.parse_args()

    _, broken_targets_count, _ = audit_quartz_links(
        public_dir=args.public_dir,
        report_file=args.report_file,
        top=args.top,
    )
    if args.fail_on_error and broken_targets_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
