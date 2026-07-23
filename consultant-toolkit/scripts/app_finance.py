"""
SCM Financial Galaxy Dashboard

任意企業の財務・SCM指標を可視化するStreamlitダッシュボード。

主な機能:
    - PPM（事業ポートフォリオマトリクス）分析 - 10年間の事業推移
    - ROIC・競合比較 - 投下資本利益率の詳細分析
    - CCC（キャッシュ・コンバージョン・サイクル）分析
    - AI戦略提案 - Gemini による経営課題診断

使用方法:
    $ streamlit run financial_scm_dashboard.py

環境変数:
    GOOGLE_API_KEY: Gemini API キー（必須）

依存パッケージ:
    streamlit, plotly, yfinance, polars, pandas, google-genai, numpy

Tab構成:
    1. 📂 全社・競合比較 (Corporate & Peers)
       - 1.1 📊 競合ベンチマーク
       - 1.2 🏢 全社ROIC動向
       - 1.3 🍕 事業セグメント分析
    2. 🌳 詳細収益・効率分析 (Profitability & Efficiency)
       - 2.1 📉 財務推移分析
       - 2.2 🌳 ROICツリー分析
       - 2.3 🔄 CCC・運転資本詳細
    3. 🏗️ 投資・将来シミュレーション (Future & Investment)
       - 3.1 🎰 What-If シミュレーター
       - 3.2 🔮 需要予測シミュレーション
       - 3.3 💸 投資効率(CAPEX/FCF)
       - 3.4 🤖 AI SCM戦略提案

作成者: consultant-toolkit project
最終更新: 2026-02-22
バージョン: 2.0.0（リファクタリング完了版）
"""

import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd  # yfinance/Streamlit互換用
import streamlit as st
import yfinance as yf
from consultant_toolkit.config_loader import get_config

# Import utility modules
from consultant_toolkit.env_loader import load_environment
from consultant_toolkit.financial_metrics import (
    DAYS_PER_YEAR,
    calculate_ccc,
    calculate_comprehensive_metrics,
    calculate_financial_metrics,
    get_val_safe,
)
from consultant_toolkit.mock_data import (
    ensure_historical_marginal_profit_data,
)
from consultant_toolkit.mock_data import (
    load_marginal_profit_data as _load_marginal_profit_data,
)
from consultant_toolkit.ui_components.corporate_peers import render_corporate_peers
from consultant_toolkit.ui_components.detail_analysis import render_detail_analysis
from consultant_toolkit.ui_components.future_simulation import render_future_simulation

# Load environment variables from .env file
load_environment()

# ========================================
# CONSTANTS & CONFIGURATION
# ========================================

# Load configuration from YAML file
_app_config = get_config()

# === Company Configuration (#12: ループで一括構築) ===
_companies_cfg = _app_config.get("companies") or {}
COMPANIES = {}
COMPANY_COLORS = {}
for _key, _val in _companies_cfg.items():
    if isinstance(_val, dict) and "display_name" in _val and "ticker" in _val:
        COMPANIES[_val["display_name"]] = _val["ticker"]
        COMPANY_COLORS[_val["display_name"]] = _val.get("color", "#888888")

# === Constants (Single Source of Truth: consultant_toolkit.constants) ===
from consultant_toolkit.constants import (  # noqa: E402
    ANIMATION_DURATION_MS,
    ANIMATION_TRANSITION_MS,
    WACC_BENCHMARK,
)

# --- UI/UX Configuration ---
st.set_page_config(
    page_title="Universal Company Analysis Dashboard",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========================================
# SIDEBAR: DYNAMIC COMPANY SELECTION
# ========================================

st.sidebar.title("🎯 企業選択")
st.sidebar.markdown("---")

# Import company search utility
try:
    from consultant_toolkit.company_search import (
        get_ticker_from_input,
        search_companies,
    )
except ImportError:
    # Fallback if module not found
    def get_ticker_from_input(user_input: str) -> tuple[str, str]:
        return user_input.strip().upper(), "ticker"

    def search_companies(query: str, max_results: int = 10) -> list[tuple[str, str]]:
        return []


# Target company input (supports both ticker and company name)
user_input = st.sidebar.text_input(
    "企業名 または ティッカー",
    value="AAPL",
    help="例: Apple, AAPL, トヨタ, 7203.T, Microsoft, MSFT",
)

# Convert input to ticker
target_ticker, search_method = get_ticker_from_input(user_input)

# Show search suggestions if typing company name
if user_input and search_method == "name_search":
    suggestions = search_companies(user_input, max_results=5)
    if suggestions and len(suggestions) > 1:
        st.sidebar.info(
            f"💡 他の候補: {', '.join([f'{name} ({ticker})' for name, ticker in suggestions[:3]])}"
        )

# Show error if name search found nothing
if (
    user_input
    and search_method == "ticker"
    and not any(c.isdigit() or c == "." for c in user_input)
    and not user_input.isupper()
):
    st.sidebar.error(
        f"❌ 「{user_input}」に一致する企業が見つかりませんでした。\n"
        "ティッカーシンボル（例: 7433.T）で直接入力してください。"
    )

# Load target company data to get name
try:
    target_ticker_obj = yf.Ticker(target_ticker)
    target_company_name = target_ticker_obj.info.get("longName", target_ticker)

    if search_method == "name_search":
        st.sidebar.success(
            f"✓ {target_company_name} ({target_ticker}) - 企業名から検索"
        )
    else:
        st.sidebar.success(f"✓ {target_company_name}")
except Exception:
    target_company_name = target_ticker
    st.sidebar.warning(f"⚠️ {target_ticker} - データ取得を試行します")

# Auto-suggest competitors
try:
    from consultant_toolkit.peer_suggestion import (
        suggest_peers_advanced,
        suggest_peers_basic,
        suggest_peers_with_ai,
    )

    # Competitor selection mode
    st.sidebar.markdown("### 競合企業")
    competitor_mode = st.sidebar.radio(
        "選択方法",
        [
            "🤖 AI提案（高精度）",
            "🔍 自動提案（高度）",
            "📋 自動提案（基本）",
            "✏️ 手動入力",
            "📁 設定から読込",
        ],
    )

    # Get suggestions based on mode
    if "AI提案" in competitor_mode:
        with st.spinner("🤖 AI が競合を分析中..."):
            suggested_peers = suggest_peers_with_ai(target_ticker, max_peers=5)
    elif "自動提案（高度）" in competitor_mode:
        with st.spinner("🔍 業界・規模を分析中..."):
            suggested_peers = suggest_peers_advanced(target_ticker, max_peers=5)
    elif "自動提案（基本）" in competitor_mode:
        suggested_peers = suggest_peers_basic(target_ticker)[:5]
    else:
        suggested_peers = []

except Exception as e:
    suggested_peers = []
    st.sidebar.warning(f"自動提案機能でエラー: {str(e)[:100]}")
    competitor_mode = st.sidebar.radio("選択方法", ["✏️ 手動入力", "📁 設定から読込"])

if "AI提案" in competitor_mode or "自動提案" in competitor_mode:
    if suggested_peers:
        # Show suggestion info
        if "AI提案" in competitor_mode:
            st.sidebar.info("🤖 AIが業界・規模・地域を分析して最適な競合を提案します")
        elif "高度" in competitor_mode:
            st.sidebar.info("🔍 業界・時価総額・地域を考慮した高度なマッチング")
        else:
            st.sidebar.info("📋 設定ファイルに基づく基本的な提案")

        selected_competitors = st.sidebar.multiselect(
            "競合企業（複数選択可）",
            options=suggested_peers,
            default=suggested_peers[: min(5, len(suggested_peers))],
            help=f"{len(suggested_peers)}社を提案しました。必要に応じて選択してください。",
        )
    else:
        st.sidebar.warning("自動提案がありません。手動入力を使用してください")
        selected_competitors = []
elif "手動入力" in competitor_mode:
    manual_input = st.sidebar.text_area(
        "競合ティッカー（改行区切り）", value="", help="例:\nAAPL\nMSFT\nGOOGL"
    )
    selected_competitors = [
        t.strip().upper() for t in manual_input.split("\n") if t.strip()
    ]
else:  # 設定から読込
    default_companies = list(COMPANIES.values())
    selected_competitors = st.sidebar.multiselect(
        "設定済み企業", options=default_companies, default=default_companies[:3]
    )


# Build dynamic company list (#1: 並列取得)
def _fetch_company_name(comp_ticker: str) -> tuple[str, str]:
    """yfinanceから企業名を取得（並列実行用）"""
    try:
        name = yf.Ticker(comp_ticker).info.get("longName", comp_ticker)
        return name, comp_ticker
    except Exception:
        return comp_ticker, comp_ticker


DYNAMIC_COMPANIES = {target_company_name: target_ticker}
peers_to_fetch = [t for t in selected_competitors if t != target_ticker]
if peers_to_fetch:
    with ThreadPoolExecutor(max_workers=8) as _executor:
        _futures = {_executor.submit(_fetch_company_name, t): t for t in peers_to_fetch}
        for _future in as_completed(_futures):
            _name, _ticker = _future.result()
            DYNAMIC_COMPANIES[_name] = _ticker

# Generate dynamic colors (#14: 20色に拡張して重複を防止)
random.seed(42)
DYNAMIC_COLORS = {}
color_palette = [
    "#e00078",
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
    "#ff9896",
    "#c5b0d5",
    "#c49c94",
    "#f7b6d2",
    "#c7c7c7",
    "#dbdb8d",
]
for i, (name, _ticker) in enumerate(DYNAMIC_COMPANIES.items()):
    DYNAMIC_COLORS[name] = color_palette[i % len(color_palette)]

st.sidebar.markdown("---")
st.sidebar.markdown(f"**選択企業数**: {len(DYNAMIC_COMPANIES)}")

# --- CSS Injection (Dark Mode & Mobile Optimization) ---
# (External CSS file loading removed - using inline CSS below instead)


# --- インラインスタイル ---
st.markdown(
    """
<style>
    .reportview-container { background: #fafafa; }
    h1 { color: #e00078; font-family: 'Helvetica Neue', sans-serif; font-weight: 800; }
    .stMetric-value { color: #e00078 !important; font-weight: 900; }
</style>
""",
    unsafe_allow_html=True,
)

st.title(f"📊 Universal Company Analysis: {target_company_name} ({target_ticker})")
st.markdown("**(AI-Powered Financial & SCM Analytics)**")

# Export buttons in header
# #9: データ未読込時はボタンを無効化してユーザーの混乱を防ぐ
_has_export_data = bool(st.session_state.get("export_data"))
export_pdf = False
export_excel = False
export_data_btn = False

try:
    cols = st.columns([1, 1, 1, 6])
    if len(cols) == 4:
        col1, col2, col3, col4 = cols
        with col1:
            export_pdf = st.button(
                "📄 PDF",
                disabled=not _has_export_data,
                help=None
                if _has_export_data
                else "分析タブを開くとデータが読み込まれます",
            )
        with col2:
            export_excel = st.button(
                "📊 Excel",
                disabled=not _has_export_data,
                help=None
                if _has_export_data
                else "分析タブを開くとデータが読み込まれます",
            )
        with col3:
            export_data_btn = st.button(
                "💾 Data",
                disabled=not _has_export_data,
                help=None
                if _has_export_data
                else "分析タブを開くとデータが読み込まれます",
            )
except ValueError:
    pass


# --- データ読み込み機能 (Caching for speed) ---
@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_financial_data(ticker_symbol: str):
    """yfinanceから財務データ取得 (pandas DataFrameで返却)"""
    ticker = yf.Ticker(ticker_symbol)
    financials = ticker.financials  # pandas DataFrame
    balance_sheet = ticker.balance_sheet  # pandas DataFrame
    return financials, balance_sheet


@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_cashflow_data(ticker_symbol: str):
    """yfinanceからキャッシュフローデータ取得 (pandas DataFrameで返却)"""
    ticker = yf.Ticker(ticker_symbol)
    cashflow = ticker.cashflow  # pandas DataFrame
    return cashflow


@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_marginal_profit_data(path: str):
    """CSV読み込み (polars DataFrameで返却)"""
    return _load_marginal_profit_data(path)


# ========================================
# FINANCIAL CALCULATION UTILITIES
# ========================================
# All financial calculation functions are imported from consultant_toolkit.financial_metrics
# Wrapper for backward compatibility:


def calculate_ccc_metrics(income_statement_df, balance_sheet_df, year):
    """Wrapper for consultant_toolkit.financial_metrics.calculate_ccc"""
    return calculate_ccc(income_statement_df, balance_sheet_df, year)


# ========================================
# EXPORT FUNCTIONALITY
# ========================================
from consultant_toolkit.export_utils import generate_markdown_report, to_excel_bytes  # noqa: E402

# --- ヘルパー関数 ---
from consultant_toolkit.ui_components.ui_helpers import load_markdown_asset  # noqa: E402

# Initialize session state for export data
if "export_data" not in st.session_state:
    st.session_state.export_data = {}

# Handle export button clicks
if export_pdf:
    st.info("📄 PDF生成機能は開発中です。Markdown形式でダウンロードできます。")
    if st.session_state.export_data:
        markdown_report = generate_markdown_report(
            target_company_name,
            target_ticker,
            st.session_state.export_data.get("metrics_df", pd.DataFrame()),
            st.session_state.export_data.get("ai_analysis", None),
        )
        st.download_button(
            label="📥 Markdownレポートをダウンロード",
            data=markdown_report,
            file_name=f"{target_ticker}_analysis_report.md",
            mime="text/markdown",
        )

if export_excel:
    if st.session_state.export_data:
        try:
            excel_bytes = to_excel_bytes(st.session_state.export_data)
            st.download_button(
                label="📥 Excelファイルをダウンロード",
                data=excel_bytes,
                file_name=f"{target_ticker}_financial_data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as e:
            st.error(f"Excel生成エラー: {e}")
    else:
        st.warning("データが読み込まれていません。分析を実行してください。")

if export_data_btn:
    if st.session_state.export_data:
        # Export all data as JSON
        json_data = {}
        for key, df in st.session_state.export_data.items():
            if isinstance(df, pd.DataFrame):
                json_data[key] = df.to_dict(orient="records")
            else:
                json_data[key] = str(df)

        st.download_button(
            label="📥 JSONデータをダウンロード",
            data=json.dumps(json_data, indent=2, ensure_ascii=False),
            file_name=f"{target_ticker}_data.json",
            mime="application/json",
        )
    else:
        st.warning("データが読み込まれていません。")

# --- タブ構成 (2階層構造) ---
main_tab1, main_tab2, main_tab3 = st.tabs(
    ["📊 全社・競合比較", "🌳 詳細収益・効率分析", "🏗️ 投資・将来シミュレーション"]
)

with main_tab1:
    render_corporate_peers(
        target_ticker,
        target_company_name,
        DYNAMIC_COMPANIES,
        DYNAMIC_COLORS,
        load_financial_data,
        calculate_financial_metrics,
        get_val_safe,
        calculate_comprehensive_metrics,
    )

with main_tab2:
    render_detail_analysis(
        target_ticker,
        target_company_name,
        DYNAMIC_COMPANIES,
        DYNAMIC_COLORS,
        load_financial_data,
        calculate_financial_metrics,
        calculate_ccc_metrics,
        get_val_safe,
        load_markdown_asset,
        ensure_historical_marginal_profit_data,
        load_marginal_profit_data,
        DAYS_PER_YEAR=DAYS_PER_YEAR,
        WACC_BENCHMARK=WACC_BENCHMARK,
        ANIMATION_DURATION_MS=ANIMATION_DURATION_MS,
        ANIMATION_TRANSITION_MS=ANIMATION_TRANSITION_MS,
    )

with main_tab3:
    render_future_simulation(
        target_ticker,
        target_company_name,
        DYNAMIC_COMPANIES,
        DYNAMIC_COLORS,
        load_financial_data,
        get_cashflow_data,
        calculate_financial_metrics,
        calculate_ccc,
        get_val_safe,
        load_markdown_asset,
        DAYS_PER_YEAR=DAYS_PER_YEAR,
        WACC_BENCHMARK=WACC_BENCHMARK,
        ANIMATION_DURATION_MS=ANIMATION_DURATION_MS,
        ANIMATION_TRANSITION_MS=ANIMATION_TRANSITION_MS,
    )
