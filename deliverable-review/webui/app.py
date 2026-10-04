"""Streamlit Web UI for deliverable-review skill.

Run:
    streamlit run ~/.claude/skills/deliverable-review/webui/app.py

The app uploads a .pptx / .docx / .pdf, runs the same checks as the CLI,
and offers downloads for the Markdown report, marked copy, sanitized
copy, and AIチェック JSON.

Run locally, nothing leaves the machine except the optional URL-liveness
HEAD requests and the optional Gemini review. When deployed to Cloud Run
(K_SERVICE is set) the caption says so.

Results are cached in st.session_state keyed by (file hash, options), so
changing a filter does not re-run the pipeline (or re-call Gemini).
"""
import sys
import io
import os
import json
import hashlib
import tempfile
from pathlib import Path
from collections import Counter, defaultdict

# Make the skill's scripts/ importable
SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import streamlit as st

import extractors
import checkers
import markers
import metadata as metadata_mod
import ai_check_extract
from review import build_report, CHECKER_LABEL, CHECKER_ORDER


# ------------------------------------------------------------
# Page config
# ------------------------------------------------------------

st.set_page_config(
    page_title="Deliverable Review",
    page_icon="📋",
    layout="wide",
)

st.title("📋 Deliverable Review")
_ON_CLOUD_RUN = bool(os.getenv("K_SERVICE"))
st.caption(
    "顧客提出前のコンサル資料 (.pptx / .docx / .pdf) を10観点の機械チェック + "
    "戦略コンサル品質チェック（ローカルルール）でレビューします。"
    + (
        "本サービスは Google Cloud Run 上で動作しており、"
        "アップロードされたファイルは処理中のみコンテナの一時領域に展開され、"
        "レスポンス返却後に破棄されます（永続保存なし）。"
        if _ON_CLOUD_RUN else
        "このPC上でローカル実行しています（ファイル自体は外部に送信されません）。"
    )
    + "Gemini 定性レビュー（既定ON）が有効な間は、本文が Gemini API"
    "（Google）に送信されます。機密資料ではサイドバーでOFFにしてください。"
)


# ------------------------------------------------------------
# Sidebar — options
# ------------------------------------------------------------

with st.sidebar:
    st.header("オプション")

    st.subheader("チェック項目")

    # デフォルトOFFのチェッカー（URL死活=ネット通信、メタデータ・著作権=ユーザー指定で既定OFF）
    DEFAULT_OFF = {"url-liveness", "metadata", "copyright"}

    # カテゴリ別に10チェッカーをグルーピング
    CHECKER_CATEGORIES = [
        ("🔒 情報漏洩", ["metadata", "internal-content"]),
        ("🤖 AI痕跡", ["url-contamination", "ai-trace"]),
        ("🔢 内容の正確性", ["numeric-integrity", "copyright", "url-liveness", "verifiable-claim"]),
        ("✍ 体裁・作法", ["consulting-style", "consulting-layout"]),
    ]

    enabled_checkers = {}
    for cat_label, checker_ids in CHECKER_CATEGORIES:
        st.markdown(f"**{cat_label}**")
        for checker in checker_ids:
            label = CHECKER_LABEL.get(checker, checker)
            default = checker not in DEFAULT_OFF
            enabled_checkers[checker] = st.checkbox(
                label,
                value=default,
                key=f"chk_{checker}",
            )

    # --- 戦略コンサル品質（案A: ローカルルール／案B: Gemini LLM） ---
    st.markdown("**🎯 戦略コンサル品質**")
    enable_strategy_rules = st.checkbox(
        "機械ルールで品質チェック（タイトル長・結論欠落等、ローカル完結）",
        value=True,
        key="chk_strategy_rules",
    )
    enable_llm_review = st.checkbox(
        "Gemini 3.8 Flash で定性レビュー（MECE・ピラミッド原則・So What?）",
        value=True,
        key="chk_llm_review",
        help="⚠️ スライド本文をGoogle Gemini APIに送信します。機密資料では注意。"
             " 既定ON（機密資料ではOFFにする）。APIキーは環境変数 GOOGLE_API_KEY（または GEMINI_API_KEY）"
             "、もしくは .env ファイル（カレント/スキル直下/ユーザーホーム、環境変数 "
             "DELIVERABLE_REVIEW_ENV_FILE で明示指定可）を使用。"
             " 💡 Claude Code から Skill として使う場合はこのチェックをONにする必要はありません"
             "（Claude 自身が AIチェック JSON を読んで定性レビューします）。",
    )

    st.markdown("---")
    st.subheader("追加の出力")
    enable_sanitize = st.checkbox(
        "サニタイズ版ファイルを生成（メタデータ・変更履歴・コメント削除）",
        value=True,
        help="メタデータ・変更履歴・コメントを削除した提出用コピーを作成します。",
    )
    enable_ai_check = st.checkbox(
        "AIチェック用データ（ピラミッド原則 / MECE / So What?）",
        value=True,
        help="スライド構造をJSON化し、LLM 向けレビュー手順書を添えて出力します。",
    )

    # URL死活チェックは checker 一覧から派生させる
    enable_liveness = enabled_checkers.get("url-liveness", False)

    # LLMレビューを有効にした場合、AIチェック JSONが必要（強制ON）
    if enable_llm_review:
        enable_ai_check = True

    st.markdown("---")
    st.caption(
        "このUIは `deliverable-review` スキル (`~/.claude/skills/deliverable-review/`) の"
        " Streamlit ラッパです。CLI は `scripts/review.py`。"
    )


# ------------------------------------------------------------
# File uploader
# ------------------------------------------------------------

uploaded = st.file_uploader(
    "資料をアップロード",
    type=["pptx", "docx", "pdf"],
    help="PowerPoint / Word / PDF のいずれか1ファイル",
)

if not uploaded:
    st.info("⬆ ファイルをアップロードしてください。")
    st.stop()


# ------------------------------------------------------------
# Run pipeline
# ------------------------------------------------------------

def run_pipeline(file_bytes: bytes, filename: str, opts: dict) -> dict:
    """Run every check once and return plain results (bytes / findings)."""
    ext = Path(filename).suffix.lower()
    stem = Path(filename).stem
    out = {"ext": ext, "stem": stem, "marked_bytes": None, "marked_name": None,
           "sanitized_bytes": None, "sanitized_name": None, "sanitize_actions": [],
           "ai_check_json_bytes": None, "ai_check_prompt_bytes": None,
           "ai_check_json_name": None, "ai_check_prompt_name": None,
           "llm_error": None, "llm_findings": []}
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        input_path = tmpdir / Path(filename).name
        input_path.write_bytes(file_bytes)

        st.write("テキスト抽出...")
        doc = extractors.extract(str(input_path))
        st.write(f"- テキストユニット: {len(doc.units)} / 場所: {len(doc.location_flags)}")

        st.write("チェッカー実行...")
        all_findings = checkers.run_all(doc, skip_liveness=not opts["liveness"],
                                        strategy=opts["strategy"])
        active = set(opts["checkers"]) | ({"strategy"} if opts["strategy"] else set())
        findings = [f for f in all_findings if f.checker in active]
        st.write(f"- 指摘件数: {len(findings)} (除外: {len(all_findings) - len(findings)})")

        # AIチェック JSON（LLMレビューの前提でもある）
        ai_check_json_path = None
        if opts["ai_check"]:
            ai_check_json_path = tmpdir / f"{stem}_aicheck.json"
            prompt_path = tmpdir / f"{stem}_aicheck_prompt.md"
            ai_check_extract.write_ai_check_json(str(input_path), str(ai_check_json_path))
            ai_check_extract.write_prompt_hint(str(prompt_path))
            out["ai_check_json_bytes"] = ai_check_json_path.read_bytes()
            out["ai_check_prompt_bytes"] = prompt_path.read_bytes()
            out["ai_check_json_name"] = ai_check_json_path.name
            out["ai_check_prompt_name"] = prompt_path.name
            st.write("- AIチェック JSON 生成")

        # 案B: LLM定性レビュー（Gemini 3.8 Flash）
        if opts["llm"] and ai_check_json_path:
            st.write("Gemini 3.8 Flash に定性レビュー依頼中... (数十秒かかります)")
            import llm_review
            llm_findings, llm_error = llm_review.run_llm_review(str(ai_check_json_path))
            out["llm_error"] = llm_error
            if llm_error:
                st.warning(f"LLMレビューエラー: {llm_error}")
            else:
                out["llm_findings"] = llm_findings
                findings.extend(llm_findings)
                st.write(f"- LLM指摘: {len(llm_findings)}件")

        st.write("Markdownレポート生成...")
        out["report_md"] = build_report(doc, findings, filename)

        if ext in (".pptx", ".docx"):
            dst = tmpdir / f"{stem}_marked{ext}"
            mark = markers.mark_pptx if ext == ".pptx" else markers.mark_docx
            mark(str(input_path), str(dst), findings)
            out["marked_bytes"] = dst.read_bytes()
            out["marked_name"] = dst.name
            st.write(f"- マーキング付き {ext} 生成")

        if opts["sanitize"]:
            dst = tmpdir / f"{stem}_sanitized{ext}"
            out["sanitize_actions"] = metadata_mod.sanitize(str(input_path), str(dst), ext)
            out["sanitized_bytes"] = dst.read_bytes()
            out["sanitized_name"] = dst.name
            st.write(f"- サニタイズ版生成: {len(out['sanitize_actions'])} アクション")

    # python-pptx handles point into the deleted temp file — keep plain data only
    for f in findings:
        f.source_handle = None
    out["findings"] = findings
    return out


file_bytes = uploaded.getvalue()
opts = {
    "checkers": sorted(c for c, on in enabled_checkers.items() if on),
    "liveness": enable_liveness,
    "strategy": enable_strategy_rules,
    "llm": enable_llm_review,
    "ai_check": enable_ai_check,
    "sanitize": enable_sanitize,
}
cache_key = (hashlib.sha256(file_bytes).hexdigest(), uploaded.name,
             json.dumps(opts, sort_keys=True))

if st.session_state.get("result_key") != cache_key:
    status = st.status("チェック実行中...", expanded=False)
    try:
        with status:
            result = run_pipeline(file_bytes, uploaded.name, opts)
        status.update(label="完了", state="complete")
    except Exception as e:
        status.update(label=f"エラー: {e}", state="error")
        st.exception(e)
        st.stop()
    st.session_state["result_key"] = cache_key
    st.session_state["result"] = result

result = st.session_state["result"]
ext = result["ext"]
stem = result["stem"]
findings = result["findings"]
llm_findings = result["llm_findings"]
llm_error = result["llm_error"]
report_md = result["report_md"]
marked_bytes, marked_name = result["marked_bytes"], result["marked_name"]
sanitized_bytes, sanitized_name = result["sanitized_bytes"], result["sanitized_name"]
sanitize_actions = result["sanitize_actions"]
ai_check_json_bytes = result["ai_check_json_bytes"]
ai_check_json_name = result["ai_check_json_name"]
ai_check_prompt_bytes = result["ai_check_prompt_bytes"]
ai_check_prompt_name = result["ai_check_prompt_name"]


# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------

sev_counts = Counter(f.severity for f in findings)
cols = st.columns(4)
cols[0].metric("HIGH", sev_counts.get("HIGH", 0))
cols[1].metric("MEDIUM", sev_counts.get("MEDIUM", 0))
cols[2].metric("LOW", sev_counts.get("LOW", 0))
cols[3].metric("INFO", sev_counts.get("INFO", 0))

if sev_counts.get("HIGH", 0) > 0:
    st.error("⚠️ HIGHレベルの指摘があります。顧客提出前に修正してください。")
elif sev_counts.get("MEDIUM", 0) > 0:
    st.warning("🟡 MEDIUMレベルの指摘があります。内容を確認してください。")
else:
    st.success("✅ HIGH/MEDIUMの指摘はありません。")


# ------------------------------------------------------------
# Gemini 3.8 Flash 定性レビュー結果
# ------------------------------------------------------------

if enable_llm_review:
    st.subheader("🤖 Gemini 3.8 Flash 定性レビュー結果")
    if llm_error:
        st.error(f"レビュー失敗: {llm_error}")
    elif not llm_findings:
        st.info("Gemini からの指摘はありませんでした。")
    else:
        cat_label = {
            "llm/pyramid": "📐 ピラミッド原則",
            "llm/mece": "🧩 MECE",
            "llm/so-what": "💡 So What? / Why So?",
            "llm/issue-tree": "🌳 Issue Tree / Key Question",
            "llm/logic-leap": "🔗 ロジック飛躍",
            "llm/data-rigor": "🔢 数値の出所と粒度",
            "llm/framework": "🧱 フレームワーク整合",
            "llm/action": "🎯 アクションの具体性",
            "llm/feasibility": "🚀 実行可能性",
            "llm/balance": "⚖️ 構成バランス",
            "llm/client-view": "👤 顧客視点",
            "llm/alternatives": "🔀 代替案の提示",
            "llm/premise": "📎 前提・限界の開示",
            "llm/story-line": "📖 Story Line",
            "llm/risk-scenario": "🌪 リスクシナリオ",
        }
        sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
        sev_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵", "INFO": "⚪"}

        # 総評（評価グレード・提出可否）を最上部に常時表示
        for f in llm_findings:
            if f.category == "llm/overall-assessment":
                st.info("**総評** — " + f.note.replace(" | ", "  \n"))

        detail = [f for f in llm_findings if f.category != "llm/overall-assessment"]
        llm_sev_counts = Counter(f.severity for f in detail)
        lc = st.columns(4)
        lc[0].metric("HIGH", llm_sev_counts.get("HIGH", 0))
        lc[1].metric("MEDIUM", llm_sev_counts.get("MEDIUM", 0))
        lc[2].metric("LOW", llm_sev_counts.get("LOW", 0))
        lc[3].metric("INFO", llm_sev_counts.get("INFO", 0))

        by_cat = defaultdict(list)
        for f in detail:
            by_cat[f.category].append(f)

        for cat_key, cat_name in cat_label.items():
            items = sorted(by_cat.get(cat_key, []), key=lambda f: sev_order.get(f.severity, 99))
            if not items:
                continue
            has_issue = any(f.severity != "INFO" for f in items)
            with st.expander(f"{cat_name} ({len(items)}件)", expanded=has_issue):
                for f in items:
                    st.markdown(
                        f"{sev_icon.get(f.severity, '⚪')} **{f.severity}** "
                        f"| {f.location_label} — {f.note}"
                    )

        other = [f for f in detail if f.category not in cat_label]
        if other:
            with st.expander(f"その他 ({len(other)}件)", expanded=False):
                for f in other:
                    st.markdown(
                        f"{sev_icon.get(f.severity, '⚪')} **{f.severity}** "
                        f"| {f.location_label} | {f.category} — {f.note}"
                    )


# ------------------------------------------------------------
# Per-checker summary table
# ------------------------------------------------------------

st.subheader("チェッカー別サマリ")
by_sev_checker = defaultdict(lambda: defaultdict(int))
for f in findings:
    by_sev_checker[f.checker][f.severity] += 1

summary_rows = []
for checker in CHECKER_ORDER:
    row = by_sev_checker.get(checker, {})
    total = sum(row.values())
    if total == 0:
        continue
    summary_rows.append({
        "チェッカー": CHECKER_LABEL.get(checker, checker),
        "HIGH": row.get("HIGH", 0),
        "MEDIUM": row.get("MEDIUM", 0),
        "LOW": row.get("LOW", 0),
        "INFO": row.get("INFO", 0),
        "計": total,
    })
if summary_rows:
    st.dataframe(summary_rows, width="stretch", hide_index=True)
else:
    st.info("発火した指摘はありません。")


# ------------------------------------------------------------
# Filtered findings table
# ------------------------------------------------------------

st.subheader("指摘詳細")

c1, c2 = st.columns([1, 3])
with c1:
    sev_filter = st.multiselect(
        "重要度",
        ["HIGH", "MEDIUM", "LOW", "INFO"],
        default=["HIGH", "MEDIUM"],
    )
with c2:
    checker_filter = st.multiselect(
        "チェッカー",
        [CHECKER_LABEL.get(c, c) for c in CHECKER_ORDER if c in by_sev_checker],
        default=[],
    )

# Build reverse label map for filtering
label_to_checker = {CHECKER_LABEL.get(c, c): c for c in CHECKER_ORDER}
active_checkers = {label_to_checker[l] for l in checker_filter} if checker_filter else None

rows = []
for f in findings:
    if sev_filter and f.severity not in sev_filter:
        continue
    if active_checkers and f.checker not in active_checkers:
        continue
    ev = f.evidence if len(f.evidence) < 120 else f.evidence[:120] + "…"
    rows.append({
        "重要度": f.severity,
        "チェッカー": CHECKER_LABEL.get(f.checker, f.checker),
        "カテゴリ": f.category,
        "場所": f.location_label,
        "該当": ev,
        "備考": f.note[:120] + ("…" if len(f.note) > 120 else ""),
    })

# Sort by severity
sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
rows.sort(key=lambda r: (sev_order.get(r["重要度"], 99), r["チェッカー"]))

st.caption(f"{len(rows)}件表示 (フィルタ適用後)")
if rows:
    st.dataframe(rows, width="stretch", hide_index=True)


# ------------------------------------------------------------
# Downloads
# ------------------------------------------------------------

st.subheader("ダウンロード")

dl_cols = st.columns(4)

dl_cols[0].download_button(
    "📄 レポート (.md)",
    data=report_md.encode("utf-8"),
    file_name=f"{stem}_review.md",
    mime="text/markdown",
    width="stretch",
)

if marked_bytes:
    mime = {
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }[ext]
    dl_cols[1].download_button(
        "🖍 マーキング付きコピー",
        data=marked_bytes,
        file_name=marked_name,
        mime=mime,
        width="stretch",
    )
else:
    dl_cols[1].caption(".pdf のためマーキング非対応")

if sanitized_bytes:
    mime = {
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
    }[ext]
    dl_cols[2].download_button(
        "🧹 サニタイズ版",
        data=sanitized_bytes,
        file_name=sanitized_name,
        mime=mime,
        width="stretch",
    )
else:
    dl_cols[2].caption("サニタイズ未実行")

if ai_check_json_bytes:
    dl_cols[3].download_button(
        "📊 AIチェック JSON",
        data=ai_check_json_bytes,
        file_name=ai_check_json_name,
        mime="application/json",
        width="stretch",
    )
    with st.expander("AIチェック レビュー手順書 (LLMに渡す)"):
        st.markdown(ai_check_prompt_bytes.decode("utf-8"))
        st.download_button(
            "📘 AIチェック プロンプト (.md)",
            data=ai_check_prompt_bytes,
            file_name=ai_check_prompt_name,
            mime="text/markdown",
        )
else:
    dl_cols[3].caption("AIチェック 未実行")


# ------------------------------------------------------------
# Sanitize actions log
# ------------------------------------------------------------

if enable_sanitize and sanitize_actions:
    with st.expander("サニタイズ処理の詳細"):
        for a in sanitize_actions:
            st.write(f"- {a}")


# ------------------------------------------------------------
# Full report preview
# ------------------------------------------------------------

with st.expander("Markdownレポート全文をプレビュー"):
    st.markdown(report_md)
