import json
import os
import re
import textwrap
import typing
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv

# --- Constants ---
CACHE_TTL_DATA = 600  # Backlog issue data: 10 minutes
CACHE_TTL_AI = 3600  # AI analysis responses: 1 hour
CACHE_TTL_COMMENTS = 300  # Backlog comments: 5 minutes
FETCH_PAGE_SIZE = 100  # Issues per API request
FETCH_SAFETY_LIMIT = 5000  # Max issues to fetch
COMMENTS_PER_ISSUE = 20  # Max comments to fetch per issue
VELOCITY_WEEKS = 16  # Weeks to display in velocity chart
VELOCITY_MOVING_AVG = 4  # Moving average window (weeks)
PREDICTION_FUTURE_DAYS = 180  # Max future days for regression forecast
GANTT_MAX_TASKS = 30  # Max tasks shown in Gantt chart
AI_MODEL = "gemini-3.1-pro-preview"

# --- Setup & Config ---
st.set_page_config(page_title="ERP PMO Galaxy Dashboard", page_icon="🌌", layout="wide")
env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(env_path)
load_dotenv()

# Fix escape sequences for Windows paths loaded from .env
gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if gac:
    if "\t" in gac:
        gac = gac.replace("\t", "\\t")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gac
    if not os.path.exists(gac):
        del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

try:
    from google.genai import types

    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


# --- Helpers ---
def render_issue_table(
    df: pd.DataFrame,
    columns: list[str],
    space: str,
    domain: str,
    hide_index: bool = True,
) -> None:
    """issueKey_url リンク列付きで st.dataframe を描画する共通ヘルパー。"""
    display = df[[c for c in columns if c in df.columns]].copy()
    display.insert(
        0,
        "issueKey_url",
        display["issueKey"].apply(lambda k: f"https://{space}.{domain}/view/{k}"),
    )
    st.dataframe(
        display,
        width="stretch",
        hide_index=hide_index,
        column_config={
            "issueKey_url": st.column_config.LinkColumn(
                label="Backlog Link", display_text="Open"
            ),
            "issueKey": "課題キー",
            "type_name": "種別",
            "priority_name": "優先度",
            "status_name": "状態",
            "category_name": "カテゴリー",
            "assignee_name": "担当者",
            "dueDate_dt": "期限日",
            "startDate_dt": "開始日",
            "summary": "件名",
            "estimatedHours": "予定",
            "actualHours": "実績",
            "Over_Hours": "超過",
        },
    )


def process_issues(raw_issues: list[dict]) -> pd.DataFrame:
    """生のBacklogイシューリストをDataFrameに変換して派生列を付与する。"""
    df = pd.DataFrame(raw_issues)
    df["created_dt"] = pd.to_datetime(df["created"]).dt.date
    df["updated_dt"] = pd.to_datetime(df["updated"]).dt.date
    df["dueDate_dt"] = pd.to_datetime(df["dueDate"], errors="coerce").dt.date
    df["startDate_dt"] = pd.to_datetime(df["startDate"], errors="coerce").dt.date

    df["status_name"] = df["status"].apply(
        lambda x: x["name"] if isinstance(x, dict) else "Unknown"
    )
    df["is_closed"] = df["status"].apply(
        lambda x: x["id"] == 4 if isinstance(x, dict) else False
    )
    df["assignee_name"] = df["assignee"].apply(
        lambda x: x["name"] if isinstance(x, dict) and x else "Unassigned"
    )
    df["type_name"] = df["issueType"].apply(
        lambda x: x["name"] if isinstance(x, dict) else "Unknown"
    )
    df["priority_name"] = df["priority"].apply(
        lambda x: x["name"] if isinstance(x, dict) else "Normal"
    )
    df["priority_id"] = df["priority"].apply(
        lambda x: x["id"] if isinstance(x, dict) else 3
    )
    # 複数カテゴリの場合は最初のものを使用
    df["category_name"] = df["category"].apply(
        lambda x: x[0]["name"] if isinstance(x, list) and len(x) > 0 else "N/A"
    )
    df["estimatedHours"] = (
        (
            df["estimatedHours"]
            if "estimatedHours" in df.columns
            else pd.Series(0.0, index=df.index)
        )
        .fillna(0)
        .astype(float)
    )
    df["actualHours"] = (
        (
            df["actualHours"]
            if "actualHours" in df.columns
            else pd.Series(0.0, index=df.index)
        )
        .fillna(0)
        .astype(float)
    )
    return df


# --- Data Fetching ---
@st.cache_data(ttl=CACHE_TTL_DATA)
def fetch_backlog_data(
    space_id: str, api_key: str, project_key: str, domain: str = "backlog.com"
) -> list[dict] | None:
    base_url = f"https://{space_id}.{domain}/api/v2"
    try:
        proj_res = requests.get(
            f"{base_url}/projects/{project_key}",
            params=typing.cast(typing.Any, {"apiKey": api_key}),
            timeout=10,
        )
        if proj_res.status_code != 200:
            st.error(f"Error fetching project: {proj_res.status_code} {proj_res.text}")
            return None
        project_id = int(proj_res.json()["id"])

        all_issues: list[dict] = []
        offset = 0
        my_bar = st.progress(0, text="Downloading Backlog data. Please wait...")

        while True:
            params_list = [
                ("apiKey", api_key),
                ("projectId[]", project_id),
                ("count", FETCH_PAGE_SIZE),
                ("offset", offset),
                ("statusId[]", 1),
                ("statusId[]", 2),
                ("statusId[]", 3),
                ("statusId[]", 4),
                ("sort", "created"),
            ]
            res = requests.get(
                f"{base_url}/issues",
                params=typing.cast(typing.Any, params_list),
                timeout=15,
            )
            if res.status_code != 200:
                st.error(f"Error fetching issues: {res.status_code}")
                break
            issues = res.json()
            if not issues:
                break
            all_issues.extend(issues)
            offset += FETCH_PAGE_SIZE
            my_bar.progress(
                min(offset / 1000, 1.0), text=f"Fetched {len(all_issues)} issues..."
            )
            if len(all_issues) > FETCH_SAFETY_LIMIT:
                st.warning(f"Reached safety limit ({FETCH_SAFETY_LIMIT} issues).")
                break

        my_bar.empty()
        return all_issues
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None


@st.cache_data(ttl=CACHE_TTL_COMMENTS)
def fetch_issue_comments(
    space_id: str, api_key: str, issue_id: str | int, domain: str = "backlog.com"
) -> list[dict]:
    """Backlog APIからissueのコメント一覧を取得する。"""
    base_url = f"https://{space_id}.{domain}/api/v2"
    try:
        res = requests.get(
            f"{base_url}/issues/{issue_id}/comments",
            params={"apiKey": api_key, "count": str(COMMENTS_PER_ISSUE)},
            timeout=10,
        )
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []


# --- AI Utils ---
def get_gemini_client(gemini_api_key: str) -> tuple[Any | None, str | None]:
    """堅牢な認証ロジックを備えたAIクライアント生成関数。"""
    if not HAS_GENAI:
        return None, "⚠️ AI SDK (google-genai) がインストールされていません。"

    use_vertex = os.getenv("USE_VERTEX_AI", "false").lower() == "true"
    gac_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if use_vertex and (not gac_env or not os.path.exists(gac_env)):
        use_vertex = False  # 安全にAPIキー認証へフォールバック

    try:
        from consultant_toolkit.gemini_client import create_gemini_client

        if use_vertex:
            client = create_gemini_client(
                use_vertex=True,
                project=os.getenv("GOOGLE_CLOUD_PROJECT"),
                location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
        else:
            if not gemini_api_key:
                return None, "❌ Gemini API Key が設定されていません。"
            client = create_gemini_client(api_key=gemini_api_key)
        return client, None
    except (ImportError, ValueError, ConnectionError) as e:
        return None, f"❌ AI Client Initialization Error: {e}"


def _call_gemini(
    client: Any, prompt: str, thinking_level: str, temperature: float
) -> str:
    """Gemini APIを呼び出してテキストを返す共通ラッパー。"""
    level_map = {
        "minimal": types.ThinkingLevel.MINIMAL,
        "medium": types.ThinkingLevel.MEDIUM,
        "high": types.ThinkingLevel.HIGH,
    }
    tl = level_map.get(thinking_level, types.ThinkingLevel.MEDIUM)
    config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            include_thoughts=(thinking_level != "minimal"),
            thinking_level=tl,
        ),
        temperature=temperature,
    )
    any_client = typing.cast(typing.Any, client)
    response = any_client.models.generate_content(
        model=AI_MODEL, contents=prompt, config=config
    )
    return response.text


@st.cache_data(ttl=CACHE_TTL_AI)
def get_ai_analysis_jp(project_summary_json: str, gemini_api_key: str) -> str:
    client, err_msg = get_gemini_client(gemini_api_key)
    if err_msg:
        return err_msg
    try:
        prompt = textwrap.dedent(f"""
            <role>
            あなたはERP導入プロジェクト（SAP S/4HANA移行など）の超有能なPMO責任者よ。
            </role>

            <data>
            分析対象となるプロジェクトデータ：
            {project_summary_json}
            </data>

            <task>
            ステアリング・コミッティ（役員向け報告会）の資料として、上記のデータを分析し、
            「プロジェクトの致命的リスク」「リソースのボトルネック」「是正勧告」をブチかましなさい。
            </task>

            <constraints>
            1. 20代前半の強気なギャル口調（「〜よ」「〜じゃない？」等）で、かつプロフェッショナルな洞察を含めること。
            2. Markdown形式で出力し、見出し（###）や箇条書きを活用すること。HTMLタグは不要。
            3. 抽象的な精神論ではなく、明日すぐに実行すべき「殲滅アクション（具体的な是正指示）」を3つ提案すること。
            4. 「銀河憲法」に基づき、ユーザーに迎合せず、客観的かつ冷徹にプロジェクトの危機的状況を警告すること。
            </constraints>

            出力は必ず以下のセクションから開始しなさい：
            ### 🚀 PMO Galaxy Analysis Report
        """).strip()
        return _call_gemini(client, prompt, thinking_level="medium", temperature=1.0)
    except Exception as e:
        return f"❌ AI Analysis Error: {e}"


@st.cache_data(ttl=CACHE_TTL_AI)
def get_ai_weekly_summary(summary_json: str, gemini_api_key: str) -> str:
    """週次サマリーレポートをGeminiで生成する。"""
    client, err_msg = get_gemini_client(gemini_api_key)
    if err_msg:
        return err_msg
    try:
        prompt = textwrap.dedent(f"""
            <role>
            あなたはERP導入プロジェクトのPMOよ。毎週月曜朝に週次報告ドラフトを作成するのが仕事。
            </role>

            <data>
            今週のプロジェクトデータ：
            {summary_json}
            </data>

            <task>
            以下の構成で週次ステータスレポートのドラフトを日本語で作成しなさい。
            そのままSlackやメールに貼り付けられる実用的な文章にすること。
            </task>

            <constraints>
            1. 出力フォーマットは必ず以下の構成に従うこと（見出しはそのまま使用）：
               ### 📋 週次ステータスレポート（ドラフト）
               **対象期間：** （先週月曜〜今週日曜）
               #### ✅ 先週の完了事項
               #### 🔥 今週の重点タスク（期限7日以内）
               #### 🚨 課題・リスク
               #### 💡 来週へのアクション
            2. 箇条書きを使い、簡潔に。1項目2行以内。
            3. 数字（件数・工数）を必ず根拠として含めること。
            4. ギャル口調は不要。プロフェッショナルな文体で。
            </constraints>
        """).strip()
        return _call_gemini(client, prompt, thinking_level="minimal", temperature=0.7)
    except Exception as e:
        return f"❌ AI Weekly Summary Error: {e}"


@st.cache_data(ttl=CACHE_TTL_COMMENTS)
def get_ai_comment_risk_analysis(comments_text: str, gemini_api_key: str) -> str:
    """コメントテキストからリスクを検知してGeminiで評価する。"""
    client, err_msg = get_gemini_client(gemini_api_key)
    if err_msg:
        return err_msg
    try:
        prompt = textwrap.dedent(f"""
            以下はBacklogプロジェクトの期限超過タスクのコメント一覧です。
            各コメントを確認し、リスクワード（遅延・困難・ブロック・確認中・未定・問題・課題・できない・待ち等）を検知して、
            各タスクを「リスクあり」「注意」「問題なし」の3段階で評価してください。

            コメントデータ:
            {comments_text}

            出力形式（Markdownの箇条書き）:
            - **[issueKey]**: [評価] — [理由（1行）]
        """).strip()
        return _call_gemini(client, prompt, thinking_level="minimal", temperature=0.5)
    except Exception as e:
        return f"❌ AI Comment Risk Analysis Error: {e}"


# --- Main App ---
def main() -> None:
    st.title("🌌 ERP PMO GALAXY DASHBOARD (Interactive v8)")
    st.markdown("---")

    # Auto-detect config from .env
    env_url = os.getenv("BACKLOG_URL", "")
    _m_space = re.search(r"https://([^.]+)\.", env_url) if env_url else None
    default_space = _m_space.group(1) if _m_space else ""
    _m_proj = re.search(r"/projects/([^/?]+)", env_url) if env_url else None
    default_proj = _m_proj.group(1) if _m_proj else ""
    _m_domain = re.search(r"backlog\.(com|jp)", env_url) if env_url else None
    default_domain = _m_domain.group(0) if _m_domain else "backlog.com"

    default_apikey = os.getenv("BACKLOG_API_KEY", "")
    gkey = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""

    with st.sidebar:
        st.header("⚙️ 設定 (Configuration)")
        space = st.text_input("Space ID", value=default_space)
        domain = st.text_input("Domain", value=default_domain)
        proj = st.text_input("Project Key", value=default_proj)
        apikey = st.text_input("Backlog API Key", value=default_apikey, type="password")

        st.markdown("---")
        st.header("🔍 フィルタリング (Filters)")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            load_data_btn = st.button("🚀 読み込み", width="stretch")
        with col_btn2:
            reload_btn = st.button(
                "🔄 リロード",
                width="stretch",
                help="キャッシュをクリアして最新データを取得します",
            )

        if "fetched_at" in st.session_state:
            st.markdown("---")
            st.caption(f"最終取得: {st.session_state['fetched_at']}")

    if not (space and proj and apikey):
        st.info(
            "👈 サイドバーにBacklogの接続情報を入力して「読み込み」をクリックしてね！"
        )
        return

    if load_data_btn or reload_btn or "raw_issues" not in st.session_state:
        if reload_btn:
            fetch_backlog_data.clear()
            st.session_state.pop("raw_issues", None)
            st.session_state.pop("fetched_at", None)
            st.toast("Refreshing data from Backlog...")

        issues = fetch_backlog_data(space, apikey, proj, domain)
        if issues:
            st.session_state["raw_issues"] = issues
            st.session_state["fetched_at"] = (
                datetime.now(UTC)
                .astimezone(timezone(timedelta(hours=9)))
                .strftime("%Y-%m-%d %H:%M JST")
            )
            st.success(f"✅ {len(issues)} 件のタスクを読み込みました！")
        else:
            st.stop()

    df = process_issues(st.session_state["raw_issues"])
    now = datetime.now(UTC).date()
    one_week_later = now + timedelta(days=7)

    # Sidebar Filters
    with st.sidebar:
        modules = ["All"] + list(df["category_name"].unique())
        selected_module = st.selectbox("モジュール (Module)", modules)

        assignees = ["All"] + list(df["assignee_name"].unique())
        selected_assignee = st.selectbox("担当者 (Assignee)", assignees)

        status_opts = ["All", "Active Only", "Closed Only"] + list(
            df["status_name"].unique()
        )
        selected_status = st.selectbox("ステータス (Status)", status_opts, index=1)

    # Apply Filters
    filtered_df = df.copy()
    if selected_module != "All":
        filtered_df = filtered_df[filtered_df["category_name"] == selected_module]
    if selected_assignee != "All":
        filtered_df = filtered_df[filtered_df["assignee_name"] == selected_assignee]
    if selected_status == "Active Only":
        filtered_df = filtered_df[~filtered_df["is_closed"]]
    elif selected_status == "Closed Only":
        filtered_df = filtered_df[filtered_df["is_closed"]]
    elif selected_status != "All":
        filtered_df = filtered_df[filtered_df["status_name"] == selected_status]

    total_active = len(filtered_df[~filtered_df["is_closed"]])
    overdue_count = len(
        filtered_df[(~filtered_df["is_closed"]) & (filtered_df["dueDate_dt"] < now)]
    )
    total_est = filtered_df["estimatedHours"].sum()
    total_act = filtered_df["actualHours"].sum()

    # --- KPI Layout ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📌 Active Tasks", total_active)
    col2.metric("🚨 Overdue Tasks", overdue_count, delta_color="inverse")
    col3.metric("⏳ Estimated Total Hours", f"{total_est:,.1f}")
    col4.metric(
        "📈 Actual Total Hours",
        f"{total_act:,.1f}",
        delta=f"{(total_act - total_est):,.1f} (Over/Under)",
        delta_color="inverse",
    )
    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        [
            "📊 Executive View (AI)",
            "🧩 Module Status",
            "👤 Resource Load",
            "🚨 Delayed & At-Risk",
            "📅 1-Week Deadlines",
            "📅 Timeline & Backlog",
            "🔍 Raw Data",
        ]
    )

    # ------------------------------------------------------------------ tab1
    with tab1:
        st.subheader("🤖 AI SteerCo Report (役員向け分析)")
        if st.button("✨ Gemini 3.1 Pro でプロジェクト状況を分析する"):
            with st.spinner("AIがプロジェクトを分析中...（少々お待ちを）"):
                summary_for_ai = {
                    "Project": proj,
                    "Total_Active": total_active,
                    "Overdue": overdue_count,
                    "Hours_Estimated": total_est,
                    "Hours_Actual": total_act,
                    "Modules_Stats": filtered_df.groupby("category_name")
                    .size()
                    .to_dict(),
                }
                ai_response = get_ai_analysis_jp(
                    json.dumps(summary_for_ai, ensure_ascii=False, indent=2), gkey
                )
                st.markdown(f"> {ai_response}")

        st.markdown("---")

        # --- AI 週次サマリー ---
        st.subheader("📝 AI 週次サマリー自動生成")
        last_week_start = now - timedelta(days=now.weekday() + 7)
        last_week_end = last_week_start + timedelta(days=6)
        completed_last_week = df[
            (df["is_closed"])
            & (df["updated_dt"] >= last_week_start)
            & (df["updated_dt"] <= last_week_end)
        ]
        imminent_tasks = filtered_df[
            (~filtered_df["is_closed"])
            & (filtered_df["dueDate_dt"] >= now)
            & (filtered_df["dueDate_dt"] <= one_week_later)
        ]

        if st.button("📄 週次レポートのドラフトを生成する"):
            with st.spinner("AIが週次レポートを作成中..."):
                weekly_data = {
                    "report_date": str(now),
                    "last_week_period": f"{last_week_start} 〜 {last_week_end}",
                    "completed_last_week": len(completed_last_week),
                    "completed_by_module": completed_last_week.groupby("category_name")
                    .size()
                    .to_dict()
                    if not completed_last_week.empty
                    else {},
                    "total_active": total_active,
                    "overdue_count": overdue_count,
                    "imminent_count": len(imminent_tasks),
                    "imminent_tasks": imminent_tasks[
                        ["issueKey", "summary", "assignee_name", "dueDate_dt"]
                    ]
                    .head(10)
                    .assign(dueDate_dt=lambda d: d["dueDate_dt"].astype(str))
                    .to_dict(orient="records"),
                    "overdue_assignees": filtered_df[
                        (~filtered_df["is_closed"]) & (filtered_df["dueDate_dt"] < now)
                    ]["assignee_name"]
                    .value_counts()
                    .head(5)
                    .to_dict(),
                    "hours_estimated": round(total_est, 1),
                    "hours_actual": round(total_act, 1),
                }
                weekly_report = get_ai_weekly_summary(
                    json.dumps(weekly_data, ensure_ascii=False, indent=2), gkey
                )
                st.markdown(weekly_report)
                st.download_button(
                    label="📥 レポートをテキストでダウンロード",
                    data=weekly_report,
                    file_name=f"weekly_report_{now}.md",
                    mime="text/markdown",
                )

        st.markdown("---")

        # --- バーンアップチャート ---
        st.subheader("📈 バーンアップチャート (Burn-up Chart)")
        burn_categories = ["All"] + list(df["category_name"].unique())
        selected_burn_cat = st.selectbox(
            "表示対象モジュール (Burn-up Target)",
            burn_categories,
            key="burnup_cat_select",
        )
        burn_target_df = (
            df
            if selected_burn_cat == "All"
            else df[df["category_name"] == selected_burn_cat]
        )

        if not burn_target_df.empty:
            date_range = pd.date_range(
                start=burn_target_df["created_dt"].min(), end=now, freq="D"
            )
            created_s = pd.to_datetime(burn_target_df["created_dt"]).dt.normalize()
            updated_s = pd.to_datetime(burn_target_df["updated_dt"]).dt.normalize()
            closed_mask = burn_target_df["is_closed"].values

            total_counts = (
                created_s.value_counts()
                .reindex(date_range, fill_value=0)
                .sort_index()
                .cumsum()
            )
            closed_counts = (
                updated_s[closed_mask]
                .value_counts()
                .reindex(date_range, fill_value=0)
                .sort_index()
                .cumsum()
                if closed_mask.any()
                else pd.Series(0, index=date_range)
            )

            burn_df = pd.DataFrame(
                {
                    "Date": date_range,
                    "Total Tasks": total_counts.values,
                    "Completed": closed_counts.values,
                }
            )

            title_suffix = (
                " (全体)" if selected_burn_cat == "All" else f" ({selected_burn_cat})"
            )
            fig_burn = go.Figure()
            fig_burn.add_trace(
                go.Scatter(
                    x=burn_df["Date"],
                    y=burn_df["Total Tasks"],
                    name=f"全タスク{title_suffix}",
                    line={"color": "#34495e", "width": 2},
                )
            )
            fig_burn.add_trace(
                go.Scatter(
                    x=burn_df["Date"],
                    y=burn_df["Completed"],
                    name=f"完了済み{title_suffix}",
                    fill="tozeroy",
                    line={"color": "#2ecc71", "width": 3},
                )
            )
            fig_burn.update_layout(height=400, margin={"l": 0, "r": 0, "t": 30, "b": 0})
            st.plotly_chart(fig_burn, width="stretch")

            # --- 納期予測（線形回帰）---
            st.subheader("🔮 納期予測 (線形回帰による完了日予測)")
            closed_all = df[df["is_closed"]].copy()
            total_tasks_all = len(df)

            if not closed_all.empty and len(closed_all) >= 2:
                all_date_range = pd.date_range(
                    start=df["created_dt"].min(), end=now, freq="D"
                )
                closed_series_all = pd.to_datetime(
                    closed_all["updated_dt"]
                ).dt.normalize()
                closed_cumsum_all = (
                    closed_series_all.value_counts()
                    .reindex(all_date_range, fill_value=0)
                    .sort_index()
                    .cumsum()
                )
                regression_df = pd.DataFrame(
                    {"Date": all_date_range, "Completed": closed_cumsum_all.values}
                )

                x_vals = np.arange(len(regression_df))
                coeffs = np.polyfit(x_vals, regression_df["Completed"].values, 1)
                slope, intercept = coeffs[0], coeffs[1]

                predicted_completion_date = None
                days_to_completion = 0
                if slope > 0:
                    days_to_completion = int((total_tasks_all - intercept) / slope)
                    predicted_completion_date = (
                        all_date_range[0] + timedelta(days=days_to_completion)
                    ).date()

                future_days = (
                    max(PREDICTION_FUTURE_DAYS, days_to_completion + 30)
                    if predicted_completion_date
                    else PREDICTION_FUTURE_DAYS
                )
                future_range = pd.date_range(
                    start=all_date_range[0], periods=len(all_date_range) + future_days
                )
                y_regression = np.clip(
                    np.polyval(coeffs, np.arange(len(future_range))), 0, total_tasks_all
                )

                fig_pred = go.Figure()
                fig_pred.add_trace(
                    go.Scatter(
                        x=regression_df["Date"],
                        y=regression_df["Completed"],
                        name="累積完了タスク数（実績）",
                        line={"color": "#2ecc71", "width": 2},
                    )
                )
                fig_pred.add_trace(
                    go.Scatter(
                        x=future_range,
                        y=y_regression,
                        name="回帰直線（予測）",
                        line={"color": "#e74c3c", "width": 2, "dash": "dash"},
                    )
                )
                if predicted_completion_date:
                    fig_pred.add_vline(
                        x=pd.Timestamp(str(predicted_completion_date)).timestamp()
                        * 1000,
                        line_dash="dot",
                        line_color="#f39c12",
                        annotation_text=f"予測完了: {predicted_completion_date}",
                        annotation_position="top left",
                    )
                fig_pred.add_hline(
                    y=total_tasks_all,
                    line_dash="dot",
                    line_color="#34495e",
                    annotation_text=f"全タスク数: {total_tasks_all}",
                    annotation_position="bottom right",
                )
                fig_pred.update_layout(
                    height=380,
                    margin={"l": 0, "r": 0, "t": 30, "b": 0},
                    xaxis_title="日付",
                    yaxis_title="累積完了タスク数",
                    legend={
                        "orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1
                    },
                )
                st.plotly_chart(fig_pred, width="stretch")

                if predicted_completion_date:
                    days_remaining = (
                        predicted_completion_date - pd.Timestamp(now).date()
                    ).days
                    st.metric(
                        label="📅 予測完了日（線形回帰）",
                        value=str(predicted_completion_date),
                        delta=f"今日から {days_remaining} 日後"
                        if days_remaining >= 0
                        else f"予定より {abs(days_remaining)} 日超過",
                        delta_color="normal" if days_remaining >= 0 else "inverse",
                    )
                else:
                    st.info(
                        "進捗が停滞しているため、完了日を予測できません。（傾きがゼロまたは負）"
                    )
            else:
                st.info("完了タスクが少なすぎるため、線形回帰による予測ができません。")
        else:
            st.info("表示するデータがありません。")

    # ------------------------------------------------------------------ tab2
    with tab2:
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("🧩 モジュール別 進捗状況")
            cat_status = (
                filtered_df.groupby(["category_name", "status_name"])
                .size()
                .reset_index(name="Count")
            )
            fig_cat = px.bar(
                cat_status,
                x="Count",
                y="category_name",
                color="status_name",
                orientation="h",
                barmode="stack",
                color_discrete_map={
                    "未対応": "#e74c3c",
                    "処理中": "#f39c12",
                    "処理済み": "#3498db",
                    "完了": "#2ecc71",
                },
            )
            st.plotly_chart(fig_cat, width="stretch")

            st.subheader("⚠️ リスク・ヒートマップ (未完了)")
            risk_summary = (
                filtered_df[~filtered_df["is_closed"]]
                .groupby(["priority_name", "status_name"])
                .size()
                .reset_index(name="Count")
            )
            if not risk_summary.empty:
                fig_risk = px.density_heatmap(
                    risk_summary,
                    x="status_name",
                    y="priority_name",
                    z="Count",
                    color_continuous_scale="Reds",
                    text_auto=True,
                )
                st.plotly_chart(fig_risk, width="stretch")
            else:
                st.info("表示するリスクデータがありません。")

        with col_b:
            st.subheader("⏱️ モジュール別 工数予実 (EVM)")
            hours_df = (
                filtered_df.groupby("category_name")[["estimatedHours", "actualHours"]]
                .sum()
                .reset_index()
            )
            fig_hours = go.Figure()
            fig_hours.add_trace(
                go.Bar(
                    x=hours_df["category_name"],
                    y=hours_df["estimatedHours"],
                    name="予定工数",
                    marker_color="#bdc3c7",
                )
            )
            fig_hours.add_trace(
                go.Bar(
                    x=hours_df["category_name"],
                    y=hours_df["actualHours"],
                    name="実績工数",
                    marker_color="#e00078",
                )
            )
            fig_hours.update_layout(barmode="group")
            st.plotly_chart(fig_hours, width="stretch")

    # ------------------------------------------------------------------ tab3
    with tab3:
        st.subheader("👤 個人別・未完了タスク負荷")
        ind_df = (
            filtered_df[~filtered_df["is_closed"]]
            .groupby(["assignee_name", "status_name"])
            .size()
            .reset_index(name="Count")
        )
        fig_ind = px.bar(
            ind_df, x="assignee_name", y="Count", color="status_name", barmode="stack"
        )
        st.plotly_chart(fig_ind, width="stretch")

        # --- ベロシティ・トレンドチャート ---
        st.subheader("📊 週次ベロシティ・トレンド (Velocity Trend)")
        closed_df = df[df["is_closed"]].copy()
        if not closed_df.empty:
            closed_df["week"] = (
                pd.to_datetime(closed_df["updated_dt"]).dt.to_period("W").dt.start_time
            )
            velocity_df = closed_df.groupby("week").size().reset_index(name="completed")
            cutoff = pd.Timestamp(now) - pd.Timedelta(weeks=VELOCITY_WEEKS)
            velocity_df = velocity_df[velocity_df["week"] >= cutoff].copy()
            velocity_df["week_label"] = velocity_df["week"].dt.strftime("%m/%d")
            velocity_df["moving_avg"] = (
                velocity_df["completed"]
                .rolling(window=VELOCITY_MOVING_AVG, min_periods=1)
                .mean()
            )

            fig_velocity = go.Figure()
            fig_velocity.add_trace(
                go.Bar(
                    x=velocity_df["week_label"],
                    y=velocity_df["completed"],
                    name="週次完了タスク数",
                    marker_color="#3498db",
                    opacity=0.7,
                )
            )
            fig_velocity.add_trace(
                go.Scatter(
                    x=velocity_df["week_label"],
                    y=velocity_df["moving_avg"],
                    name=f"{VELOCITY_MOVING_AVG}週移動平均",
                    line={"color": "#e74c3c", "width": 2, "dash": "dash"},
                )
            )
            fig_velocity.update_layout(
                height=350,
                margin={"l": 0, "r": 0, "t": 30, "b": 0},
                xaxis_title="週（月/日）",
                yaxis_title="完了タスク数",
                legend={
                    "orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1
                },
            )
            st.plotly_chart(fig_velocity, width="stretch")

            recent_4w = velocity_df.tail(VELOCITY_MOVING_AVG)["completed"].mean()
            prev_4w = (
                velocity_df.iloc[-8:-4]["completed"].mean()
                if len(velocity_df) >= 8
                else None
            )
            v_col1, v_col2 = st.columns(2)
            v_col1.metric(
                label=f"直近{VELOCITY_MOVING_AVG}週 平均ベロシティ",
                value=f"{recent_4w:.1f} タスク/週",
            )
            if prev_4w is not None:
                delta = recent_4w - prev_4w
                v_col2.metric(
                    label="前4週比",
                    value=f"{recent_4w:.1f} タスク/週",
                    delta=f"{delta:+.1f} (前4週: {prev_4w:.1f})",
                    delta_color="normal",
                )
            else:
                v_col2.metric(
                    label="前4週比", value="データ不足", delta="8週分以上で表示"
                )
        else:
            st.info("完了タスクがないためベロシティを計算できません。")

    # ------------------------------------------------------------------ tab4
    with tab4:
        st.subheader("🚨 期限超過タスク (Overdue Tasks)")
        overdue_list = filtered_df[
            (~filtered_df["is_closed"]) & (filtered_df["dueDate_dt"] < now)
        ].sort_values("dueDate_dt")
        if not overdue_list.empty:
            st.error(
                f"{len(overdue_list)}件の期限超過タスクがあります。直ちにフォローアップしてください。"
            )
            render_issue_table(
                overdue_list,
                [
                    "issueKey",
                    "type_name",
                    "priority_name",
                    "summary",
                    "category_name",
                    "assignee_name",
                    "dueDate_dt",
                ],
                space,
                domain,
            )
        else:
            st.success("素晴らしい！現在、期限を超過しているタスクはありません。")

        st.subheader("⚠️ 期限間近の重要タスク (Next 7 Days)")
        imminent_list = filtered_df[
            (~filtered_df["is_closed"])
            & (filtered_df["dueDate_dt"] >= now)
            & (filtered_df["dueDate_dt"] <= one_week_later)
        ].sort_values("dueDate_dt")
        if not imminent_list.empty:
            st.warning(
                f"今後7日以内に期限を迎えるタスクが {len(imminent_list)} 件あります。"
            )
            render_issue_table(
                imminent_list,
                ["issueKey", "type_name", "priority_name", "summary", "assignee_name", "dueDate_dt"],
                space,
                domain,
            )
        else:
            st.info("今後7日以内に期限を迎えるタスクはありません。")

        st.subheader("💸 工数超過・炎上リスクタスク (Over Budget Tasks)")
        over_budget_list = filtered_df[
            (~filtered_df["is_closed"])
            & (filtered_df["estimatedHours"] > 0)
            & (filtered_df["actualHours"] > filtered_df["estimatedHours"])
        ].copy()
        if not over_budget_list.empty:
            over_budget_list["Over_Hours"] = (
                over_budget_list["actualHours"] - over_budget_list["estimatedHours"]
            )
            over_budget_list = over_budget_list.sort_values(
                "Over_Hours", ascending=False
            )
            st.warning(
                f"{len(over_budget_list)}件のタスクが予定工数を超過して消化されています。"
            )
            render_issue_table(
                over_budget_list,
                [
                    "issueKey",
                    "type_name",
                    "summary",
                    "assignee_name",
                    "estimatedHours",
                    "actualHours",
                    "Over_Hours",
                ],
                space,
                domain,
            )
        else:
            st.info(
                "現在、予定工数を大幅に超過しているアクティブなタスクはありません。"
            )

        # --- コメントリスク分析 ---
        st.markdown("---")
        st.subheader("🔬 コメントリスク分析")
        if not overdue_list.empty:
            if st.button("🔍 期限超過タスクのコメントをAI分析する"):
                with st.spinner("Backlog APIからコメントを取得してAIが分析中..."):
                    all_comments_text = ""
                    for _, row in overdue_list.head(5).iterrows():
                        issue_id = row.get("id", row.get("issueKey", ""))
                        comments = fetch_issue_comments(space, apikey, issue_id, domain)
                        bodies = " / ".join(
                            c.get("content", "") for c in comments if c.get("content")
                        )
                        all_comments_text += (
                            f"\n**{row['issueKey']}**: {bodies or '(コメントなし)'}\n"
                        )

                    if HAS_GENAI and gkey:
                        st.markdown(
                            get_ai_comment_risk_analysis(all_comments_text, gkey)
                        )
                    else:
                        st.warning(
                            "Gemini APIキーが設定されていないため、AI分析はスキップされました。"
                        )
                        st.text(all_comments_text)
        else:
            st.info("期限超過タスクがないため、コメントリスク分析は不要です。")

    # ------------------------------------------------------------------ tab5
    with tab5:
        st.subheader("📅 1週間以内のタスク一覧 (Imminent Deadlines)")
        st.markdown(
            f"現在の日付: **{now}** から 1週間後: **{one_week_later}** までの期限タスクを表示します。"
        )
        deadline_df = filtered_df[
            (~filtered_df["is_closed"])
            & (filtered_df["dueDate_dt"] >= now)
            & (filtered_df["dueDate_dt"] <= one_week_later)
        ].sort_values("dueDate_dt")
        if not deadline_df.empty:
            col_d1, col_d2 = st.columns([1, 2])
            with col_d1:
                st.write("**モジュール別件数**")
                st.table(deadline_df["category_name"].value_counts())
            with col_d2:
                st.plotly_chart(
                    px.pie(deadline_df, names="assignee_name", title="担当者別配分"),
                    width="stretch",
                )
            st.write("**詳細リスト**")
            render_issue_table(
                deadline_df,
                [
                    "issueKey",
                    "type_name",
                    "priority_name",
                    "summary",
                    "category_name",
                    "assignee_name",
                    "dueDate_dt",
                    "status_name",
                ],
                space,
                domain,
            )
        else:
            st.balloons()
            st.success("直近1週間以内に期限を迎えるタスクはありません！平和ね！")

    # ------------------------------------------------------------------ tab6
    with tab6:
        st.subheader("📅 直近の重要マイルストーン (Gantt)")
        gantt_df = filtered_df[
            (~filtered_df["is_closed"])
            & filtered_df["startDate_dt"].notnull()
            & filtered_df["dueDate_dt"].notnull()
        ].copy()
        if not gantt_df.empty:
            gantt_df = gantt_df.sort_values("dueDate_dt").head(GANTT_MAX_TASKS)
            gantt_df["Start"] = pd.to_datetime(gantt_df["startDate_dt"])
            gantt_df["Finish"] = pd.to_datetime(gantt_df["dueDate_dt"])
            gantt_df["TaskName"] = (
                gantt_df["issueKey"]
                + ": "
                + gantt_df["summary"].str.slice(0, 30)
                + "..."
            )
            gantt_height = max(400, len(gantt_df) * 28 + 100)
            fig_gantt = px.timeline(
                gantt_df,
                x_start="Start",
                x_end="Finish",
                y="TaskName",
                color="priority_name",
                hover_data=["assignee_name", "category_name"],
            )
            fig_gantt.update_yaxes(autorange="reversed")
            fig_gantt.update_layout(
                height=gantt_height, margin={"l": 0, "r": 0, "t": 30, "b": 0}
            )
            st.plotly_chart(fig_gantt, width="stretch")
        else:
            st.info(
                "ガントチャートを表示するための「開始日」「期限日」が設定されたアクティブタスクがありません。"
            )

    # ------------------------------------------------------------------ tab7
    with tab7:
        st.subheader("🔍 データテーブル (Filtered)")

        # タスク詳細ドロワー
        if not filtered_df.empty and "issueKey" in filtered_df.columns:
            selected_issue_key = st.selectbox(
                "🔎 タスク詳細を確認する (Issue Key を選択)",
                options=["-- 選択してください --"] + filtered_df["issueKey"].tolist(),
                key="tab7_detail_selectbox",
            )
            if selected_issue_key != "-- 選択してください --":
                row = filtered_df[filtered_df["issueKey"] == selected_issue_key].iloc[0]
                with st.expander(f"📋 タスク詳細: {selected_issue_key}", expanded=True):
                    dc1, dc2 = st.columns(2)
                    with dc1:
                        st.markdown(f"**Summary:** {row.get('summary', 'N/A')}")
                        st.markdown(f"**Status:** {row.get('status_name', 'N/A')}")
                        st.markdown(f"**Priority:** {row.get('priority_name', 'N/A')}")
                        st.markdown(f"**Assignee:** {row.get('assignee_name', 'N/A')}")
                        st.markdown(f"**Category:** {row.get('category_name', 'N/A')}")
                    with dc2:
                        st.markdown(
                            f"**Estimated Hours:** {row.get('estimatedHours', 'N/A')}"
                        )
                        st.markdown(
                            f"**Actual Hours:** {row.get('actualHours', 'N/A')}"
                        )
                        st.markdown(f"**Start Date:** {row.get('startDate_dt', 'N/A')}")
                        st.markdown(f"**Due Date:** {row.get('dueDate_dt', 'N/A')}")
                    description = (
                        row.get("description") if "description" in row.index else None
                    )
                    desc_text = (
                        description
                        if description and str(description) not in ("nan", "None", "")
                        else "N/A"
                    )
                    st.markdown("**Description:**")
                    st.text_area(
                        "description_area",
                        value=desc_text,
                        height=120,
                        disabled=True,
                        label_visibility="collapsed",
                    )

        display_cols = [
            "issueKey",
            "type_name",
            "summary",
            "status_name",
            "priority_name",
            "category_name",
            "assignee_name",
            "estimatedHours",
            "actualHours",
            "startDate_dt",
            "dueDate_dt",
        ]
        render_issue_table(filtered_df, display_cols, space, domain, hide_index=False)


if __name__ == "__main__":
    main()
