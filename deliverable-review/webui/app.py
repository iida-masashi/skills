"""Streamlit Web UI for deliverable-review skill.

Run:
    streamlit run ~/.claude/skills/deliverable-review/webui/app.py

The app uploads a .pptx / .docx / .pdf, runs the same checks as the CLI,
and offers downloads for the Markdown report, marked copy, sanitized
copy, and AIチェック JSON.

Everything runs locally — no external API calls are made except the
optional URL-liveness HEAD requests (disabled by default in the UI).
"""
import sys
import io
import json
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
st.caption(
    "顧客提出前のコンサル資料 (.pptx / .docx / .pdf) を10観点の機械チェック + "
    "戦略コンサル品質チェック（ローカルルール）でレビューします。"
    "本サービスは Google Cloud Run（asia-northeast1）上で動作しており、"
    "アップロードされたファイルは処理中のみコンテナの一時領域に展開され、"
    "レスポンス返却後に破棄されます（永続保存なし）。"
    "Gemini 定性レビューを有効にした場合のみ、スライド本文が Gemini API"
    "（Google）にも送信されます。機密資料の取り扱いは利用者の責任で判断してください。"
)


# ------------------------------------------------------------
# Sidebar — options
# ------------------------------------------------------------

with st.sidebar:
    st.header("オプション")

    st.subheader("チェック項目")

    # デフォルトOFFにしたいチェッカー（ネット通信/重い処理）
    DEFAULT_OFF = {"url-liveness"}

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
        "Gemini 3.1 Pro で定性レビュー（MECE・ピラミッド原則・So What?）",
        value=False,
        key="chk_llm_review",
        help="⚠️ スライド本文をGoogle Gemini APIに送信します。機密資料では注意。"
             " 既定OFF。APIキーは環境変数 GOOGLE_API_KEY（または GEMINI_API_KEY）"
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

with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    ext = Path(uploaded.name).suffix.lower()
    stem = Path(uploaded.name).stem

    input_path = tmpdir / uploaded.name
    input_path.write_bytes(uploaded.getvalue())

    status = st.status("チェック実行中...", expanded=False)
    try:
        with status:
            st.write("テキスト抽出...")
            doc = extractors.extract(str(input_path))
            st.write(f"- テキストユニット: {len(doc.units)} / 場所: {len(doc.location_flags)}")

            st.write("チェッカー実行...")
            all_findings = checkers.run_all(doc, skip_liveness=not enable_liveness)
            active = {c for c, on in enabled_checkers.items() if on}
            findings = [f for f in all_findings if f.checker in active]
            st.write(f"- 指摘件数: {len(findings)} (除外: {len(all_findings) - len(findings)})")

            # 案A: 戦略コンサル品質（機械ルール）
            if enable_strategy_rules:
                st.write("戦略コンサル品質チェック（機械ルール）...")
                import strategy_checks
                sf = strategy_checks.run_strategy_checks(doc)
                findings.extend(sf)
                st.write(f"- 追加指摘: {len(sf)}件")

            # AIチェック JSON（LLMレビューの前提でもある）
            ai_check_json_bytes = None
            ai_check_prompt_bytes = None
            ai_check_json_name = None
            ai_check_prompt_name = None
            ai_check_json_path = None
            if enable_ai_check:
                ai_check_json_path = tmpdir / f"{stem}_aicheck.json"
                prompt_path = tmpdir / f"{stem}_aicheck_prompt.md"
                ai_check_extract.write_ai_check_json(str(input_path), str(ai_check_json_path))
                ai_check_extract.write_prompt_hint(str(prompt_path))
                ai_check_json_bytes = ai_check_json_path.read_bytes()
                ai_check_prompt_bytes = prompt_path.read_bytes()
                ai_check_json_name = ai_check_json_path.name
                ai_check_prompt_name = prompt_path.name
                st.write(f"- AIチェック JSON 生成")

            # 案B: LLM定性レビュー（Gemini 3.1 Pro）
            llm_error = None
            llm_findings = []
            if enable_llm_review and ai_check_json_path:
                st.write("Gemini 3.1 Pro に定性レビュー依頼中... (数十秒かかります)")
                import llm_review
                llm_findings, llm_error = llm_review.run_llm_review(str(ai_check_json_path))
                if llm_error:
                    st.warning(f"LLMレビューエラー: {llm_error}")
                else:
                    findings.extend(llm_findings)
                    st.write(f"- LLM指摘: {len(llm_findings)}件")

            st.write("Markdownレポート生成...")
            report_md = build_report(doc, findings, str(input_path))

            marked_bytes = None
            marked_name = None
            if ext == ".pptx":
                dst = tmpdir / f"{stem}_marked.pptx"
                markers.mark_pptx(str(input_path), str(dst), findings)
                marked_bytes = dst.read_bytes()
                marked_name = dst.name
                st.write(f"- マーキング付き .pptx 生成")
            elif ext == ".docx":
                dst = tmpdir / f"{stem}_marked.docx"
                markers.mark_docx(str(input_path), str(dst), findings)
                marked_bytes = dst.read_bytes()
                marked_name = dst.name
                st.write(f"- マーキング付き .docx 生成")

            sanitized_bytes = None
            sanitized_name = None
            sanitize_actions = []
            if enable_sanitize:
                dst = tmpdir / f"{stem}_sanitized{ext}"
                sanitize_actions = metadata_mod.sanitize(str(input_path), str(dst), ext)
                sanitized_bytes = dst.read_bytes()
                sanitized_name = dst.name
                st.write(f"- サニタイズ版生成: {len(sanitize_actions)} アクション")

        status.update(label="完了", state="complete")
    except Exception as e:
        status.update(label=f"エラー: {e}", state="error")
        st.exception(e)
        st.stop()


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
# Gemini 3.1 Pro 定性レビュー結果
# ------------------------------------------------------------

if enable_llm_review:
    st.subheader("🤖 Gemini 3.1 Pro 定性レビュー結果")
    if llm_error:
        st.error(f"レビュー失敗: {llm_error}")
    elif not llm_findings:
        st.info("Gemini からの指摘はありませんでした。")
    else:
        # カテゴリ別にグルーピング
        cat_label = {
            "llm/pyramid": "📐 ピラミッド原則",
            "llm/mece": "🧩 MECE",
            "llm/so-what": "💡 So What? / Why So?",
            "llm/action": "🎯 アクションの具体性",
            "llm/balance": "⚖️ 構成バランス",
            "llm/client-view": "👤 顧客視点",
            "llm/quality": "✨ コンサル品質",
            "llm/logic-leap": "🔗 ロジック飛躍",
            "llm/framework": "🧱 フレームワーク整合",
            "llm/feasibility": "🚀 実行可能性",
        }
        llm_sev_counts = Counter(f.severity for f in llm_findings)
        lc = st.columns(4)
        lc[0].metric("HIGH", llm_sev_counts.get("HIGH", 0))
        lc[1].metric("MEDIUM", llm_sev_counts.get("MEDIUM", 0))
        lc[2].metric("LOW", llm_sev_counts.get("LOW", 0))
        lc[3].metric("INFO", llm_sev_counts.get("INFO", 0))

        # カテゴリでグルーピング表示
        by_cat = defaultdict(list)
        for f in llm_findings:
            by_cat[f.category].append(f)

        sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
        sev_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵", "INFO": "⚪"}

        for cat_key in ["llm/pyramid", "llm/mece", "llm/so-what",
                        "llm/action", "llm/balance", "llm/client-view", "llm/quality",
                        "llm/logic-leap", "llm/framework", "llm/feasibility"]:
            items = by_cat.get(cat_key, [])
            if not items:
                continue
            items.sort(key=lambda f: sev_order.get(f.severity, 99))
            with st.expander(f"{cat_label.get(cat_key, cat_key)} ({len(items)}件)", expanded=True):
                for f in items:
                    st.markdown(
                        f"{sev_icon.get(f.severity, '⚪')} **{f.severity}** "
                        f"| {f.location_label} — {f.note}"
                    )

        # その他カテゴリ
        known = {"llm/pyramid", "llm/mece", "llm/so-what", "llm/action",
                 "llm/balance", "llm/client-view", "llm/quality",
                 "llm/logic-leap", "llm/framework", "llm/feasibility"}
        other = [f for f in llm_findings if f.category not in known]
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
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)
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
    st.dataframe(rows, use_container_width=True, hide_index=True)


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
    use_container_width=True,
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
        use_container_width=True,
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
        use_container_width=True,
    )
else:
    dl_cols[2].caption("サニタイズ未実行")

if ai_check_json_bytes:
    dl_cols[3].download_button(
        "📊 AIチェック JSON",
        data=ai_check_json_bytes,
        file_name=ai_check_json_name,
        mime="application/json",
        use_container_width=True,
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
