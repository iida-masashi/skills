"""deliverable-review CLI entry point.

Usage:
  python review.py <path/to/file.pptx|.docx|.pdf> [--skip-liveness] [--out-dir DIR]

Outputs (next to input file unless --out-dir given):
  <stem>_review.md        — Markdown report (always)
  <stem>_marked.pptx      — .pptx with annotation boxes (pptx input only)
  <stem>_marked.docx      — .docx with summary box (docx input only)
"""
import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime

# Local imports (scripts dir on sys.path)
sys.path.insert(0, str(Path(__file__).parent))

import extractors
import checkers
import markers


SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}

CHECKER_LABEL = {
    "url-contamination": "URL汚染",
    "ai-trace": "AI生成痕跡",
    "copyright": "著作権リスク",
    "url-liveness": "URL死活",
    "verifiable-claim": "検証要主張",
    "numeric-integrity": "数値整合性",
    "metadata": "メタデータ",
    "internal-content": "内部コンテンツ",
    "consulting-style": "コンサル作法(文体)",
    "consulting-layout": "コンサル作法(体裁)",
}

CHECKER_ORDER = [
    "metadata",
    "internal-content",
    "url-contamination",
    "ai-trace",
    "numeric-integrity",
    "consulting-style",
    "consulting-layout",
    "copyright",
    "url-liveness",
    "verifiable-claim",
]


def build_report(doc, findings, input_path):
    lines = []
    lines.append(f"# Deliverable Review Report")
    lines.append("")
    lines.append(f"- **対象ファイル**: `{input_path}`")
    lines.append(f"- **生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **総指摘件数**: {len(findings)}")
    lines.append("")

    # Summary table
    by_sev_checker = defaultdict(lambda: defaultdict(int))
    for f in findings:
        by_sev_checker[f.checker][f.severity] += 1

    lines.append("## サマリー")
    lines.append("")
    lines.append("| チェッカー | HIGH | MEDIUM | LOW | INFO | 計 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for checker in CHECKER_ORDER:
        row = by_sev_checker.get(checker, {})
        total = sum(row.values())
        lines.append(
            f"| {CHECKER_LABEL[checker]} ({checker}) "
            f"| {row.get('HIGH', 0)} | {row.get('MEDIUM', 0)} | "
            f"{row.get('LOW', 0)} | {row.get('INFO', 0)} | {total} |"
        )
    lines.append("")

    # Severity legend
    lines.append("## 重要度の目安")
    lines.append("")
    lines.append("- **HIGH**: 顧客提出前に必ず修正すべき (AIツール由来URLや死亡リンク等)")
    lines.append("- **MEDIUM**: 要確認 (トラッキングパラメータ、AI定型句、出典欠如)")
    lines.append("- **LOW**: 軽微 (Markdown残骸、表の出典記載等)")
    lines.append("- **INFO**: 参考情報 (検証要主張リスト - 人間による裏取り用)")
    lines.append("")

    # Group findings by checker → by location → by severity
    findings_sorted = sorted(
        findings,
        key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.checker, f.location_index),
    )

    lines.append("## 指摘詳細")
    lines.append("")

    for checker in CHECKER_ORDER:
        ch_findings = [f for f in findings_sorted if f.checker == checker]
        if not ch_findings:
            continue
        lines.append(f"### {CHECKER_LABEL[checker]} ({checker})")
        lines.append("")
        lines.append("| # | 重要度 | 場所 | カテゴリ | 該当箇所 | 備考 |")
        lines.append("|---:|---|---|---|---|---|")
        for i, f in enumerate(ch_findings, start=1):
            ev = f.evidence.replace("|", "\\|").replace("\n", " ")
            if len(ev) > 100:
                ev = ev[:100] + "…"
            note = f.note.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {i} | {f.severity} | {f.location_label} | {f.category} | `{ev}` | {note} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 運用ガイド")
    lines.append("")
    lines.append("1. **HIGH** を順に処理。AIツール由来URL・死亡リンクは即修正。")
    lines.append("2. **MEDIUM** の出典欠如を補完、AI定型句を校正。")
    lines.append("3. **LOW** はスタイル調整。")
    lines.append("4. **INFO (検証要主張)** を手作業で裏取り。一次情報の出典を資料に追記。")
    lines.append("")
    lines.append("*このレポートは `deliverable-review` スキルによって自動生成されました。*")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Pre-delivery review for consulting deliverables")
    ap.add_argument("input", help="Path to .pptx / .docx / .pdf")
    ap.add_argument("--skip-liveness", action="store_true", help="Skip URL HEAD-request check")
    ap.add_argument("--out-dir", default=None, help="Output directory (default: same as input)")
    ap.add_argument("--sanitize", action="store_true",
                    help="Also produce <stem>_sanitized.<ext> with metadata/comments removed "
                         "(core/app properties, revisions, Word comments & tracked changes, PDF /Info).")
    ap.add_argument("--ai-check-json", dest="ai_check_json", action="store_true",
                    help="Also produce <stem>_aicheck.json (structured slide/page content) "
                         "and <stem>_aicheck_prompt.md (review instructions) for an LLM "
                         "to perform qualitative consulting review (pyramid / MECE / So What?).")
    args = ap.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"ERROR: file not found: {input_path}", file=sys.stderr)
        sys.exit(2)

    ext = input_path.suffix.lower()
    if ext not in (".pptx", ".docx", ".pdf"):
        print(f"ERROR: unsupported extension {ext} (expected .pptx/.docx/.pdf)", file=sys.stderr)
        sys.exit(2)

    out_dir = Path(args.out_dir).resolve() if args.out_dir else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem

    print(f"[1/4] Extracting text from {input_path.name}...")
    doc = extractors.extract(str(input_path))
    print(f"      {len(doc.units)} text units, {len(doc.location_flags)} locations")

    print(f"[2/4] Running checkers (skip_liveness={args.skip_liveness})...")
    findings = checkers.run_all(doc, skip_liveness=args.skip_liveness)
    print(f"      {len(findings)} findings")

    print(f"[3/4] Writing Markdown report...")
    report_path = out_dir / f"{stem}_review.md"
    report_path.write_text(build_report(doc, findings, str(input_path)), encoding="utf-8")
    print(f"      {report_path}")

    print(f"[4/4] Writing marked copy...")
    if ext == ".pptx":
        dst = out_dir / f"{stem}_marked.pptx"
        markers.mark_pptx(str(input_path), str(dst), findings)
        print(f"      {dst}")
    elif ext == ".docx":
        dst = out_dir / f"{stem}_marked.docx"
        markers.mark_docx(str(input_path), str(dst), findings)
        print(f"      {dst}")
    else:
        print(f"      (.pdf: report only, no marked copy)")

    if args.sanitize:
        print(f"[+] Sanitizing metadata...")
        import metadata as metadata_mod
        san_path = out_dir / f"{stem}_sanitized{ext}"
        actions = metadata_mod.sanitize(str(input_path), str(san_path), ext)
        print(f"      {san_path}")
        for a in actions:
            print(f"       - {a}")

    if args.ai_check_json:
        print(f"[+] Extracting AIチェック structure JSON...")
        import ai_check_extract
        json_path = out_dir / f"{stem}_aicheck.json"
        prompt_path = out_dir / f"{stem}_aicheck_prompt.md"
        ai_check_extract.write_ai_check_json(str(input_path), str(json_path))
        ai_check_extract.write_prompt_hint(str(prompt_path))
        print(f"      {json_path}")
        print(f"      {prompt_path}")
        print(f"      → 次ステップ (Claude Code から呼ばれた場合):")
        print(f"         Claude 自身が {stem}_aicheck.json を Read し、")
        print(f"         {stem}_aicheck_prompt.md の15観点（戦略コンサル品質）で定性レビューを書き出してください。")
        print(f"         **外部LLM API (Gemini/Claude API) は呼ばない。**")

    # Quick console summary
    from collections import Counter
    sev_counts = Counter(f.severity for f in findings)
    print()
    print("Summary:", dict(sev_counts))
    if sev_counts.get("HIGH", 0) > 0:
        print("[!] HIGH-severity findings present - review before delivery.")


if __name__ == "__main__":
    main()
