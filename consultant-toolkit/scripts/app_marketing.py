import json
import os
import random
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# Import utility modules
from consultant_toolkit.env_loader import get_api_key, load_environment
from duckduckgo_search import DDGS
from pytrends.request import TrendReq

# --- Page Config ---
st.set_page_config(
    page_title="Professional Marketing Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Constants ---
PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToAdd": [
        "drawline",
        "drawopenpath",
        "drawrect",
        "eraseshape",
        "togglespikelines",
        "resetViews",
    ],
}


# --- CSS Injection (Mobile Optimization & Styling) ---
def local_css(content: str):
    st.markdown(f"<style>{content}</style>", unsafe_allow_html=True)


local_css("""
    @media screen and (max-width: 768px) {
        div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
    }
    .main .block-container { padding-top: 2rem; }
    .stMetric { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border: 1px solid #e9ecef; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f1f3f5;
        border-radius: 5px 5px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] { background-color: #e7f5ff; }
""")

# --- Helper Functions ---
load_environment()


def get_genai_client(api_key):
    """Initialize Gemini client with proper mode."""
    from consultant_toolkit.gemini_client import create_gemini_client

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    is_vertex = api_key.startswith("AQ") if api_key else False

    try:
        if is_vertex and project:
            return create_gemini_client(use_vertex=True, project=project)
        else:
            return create_gemini_client(api_key=api_key)
    except (ImportError, ValueError, ConnectionError) as e:
        st.error(f"Client Init Error: {e}")
        return None


def call_gemini(api_key, prompt):
    """Universal Gemini caller with model fallback."""
    client = get_genai_client(api_key)
    if not client:
        return None

    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite-preview", "gemini-1.5-flash"]
    for model_name in models:
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            return response.text
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                continue
            return f"Error: {e}"
    return "All models failed."


def generate_insight(api_key, context_type, data_summary):
    """Generate AI insight in 'Professional Gal' persona."""
    prompt = f"""以下のデータ概要に基づき、プロフェッショナルかつ自信に満ちた「バリキャリギャル」の口調で、2〜3文のマーケティングインサイトを生成してください。

    コンテキスト: {context_type}
    データ概要: {data_summary}

    トーン指針:
    - 論理的だが、語尾は「〜だね」「〜っしょ」「〜じゃん」「〜じゃない？」など、明るく自信に満ちたハキハキした口調。
    - 専門用語（エンゲージメント、LTV、ファネル等）を交えつつも、親しみやすさと勢いを感じさせる。
    - 2〜3文で簡潔に。
    - 日本語で出力してください。
    """
    return call_gemini(api_key, prompt)


@st.cache_data(ttl=3600)
def get_google_trends(keywords, timeframe="today 12-m", geo="JP"):
    """Fetch Google Trends data."""
    try:
        pytrends = TrendReq(hl="ja-JP", tz=360)
        keywords = keywords[:5]
        pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo=geo)
        df_time = pytrends.interest_over_time()
        if not df_time.empty:
            df_time = df_time.drop(columns=["isPartial"])
        df_region = pytrends.interest_by_region(
            resolution="COUNTRY", inc_low_vol=True, inc_geo_code=False
        )
        related_queries = pytrends.related_queries()
        return df_time, df_region, related_queries
    except Exception:
        return None, None, None


@st.cache_data(ttl=3600)
def search_opinions(keyword, max_results=10, time_limit=None):
    """Search for reviews and opinions using DuckDuckGo."""
    results = []
    queries = [f"{keyword} 評判", f"{keyword} 感想"]
    try:
        with DDGS() as ddgs:
            for q in queries:
                try:
                    search_res = list(
                        ddgs.text(
                            q,
                            region="jp-jp",
                            safesearch="off",
                            max_results=5,
                            timelimit=time_limit,
                        )
                    )
                    for r in search_res:
                        results.append(
                            {
                                "title": r.get("title", ""),
                                "snippet": r.get("body", ""),
                                "link": r.get("href", ""),
                                "source": "Web",
                            }
                        )
                except Exception:
                    pass
                time.sleep(0.5)
            if len(results) < 3:
                try:
                    news_res = list(
                        ddgs.news(
                            keyword,
                            region="jp-jp",
                            safesearch="off",
                            max_results=5,
                            timelimit=time_limit,
                        )
                    )
                    for r in news_res:
                        results.append(
                            {
                                "title": r.get("title", ""),
                                "snippet": r.get("body", ""),
                                "link": r.get("url", ""),
                                "source": "News",
                            }
                        )
                except Exception:
                    pass
    except Exception:
        pass
    unique = {r["link"]: r for r in results if r["link"]}
    return list(unique.values())[:max_results]


@st.cache_data(ttl=1800)
def search_latest_news(keyword, max_results=10):
    """Search for latest news."""
    results = []
    try:
        with DDGS() as ddgs:
            news_res = list(
                ddgs.news(
                    keyword, region="jp-jp", safesearch="off", max_results=max_results
                )
            )
            for r in news_res:
                results.append(
                    {
                        "title": r["title"],
                        "link": r["url"],
                        "published": r["date"],
                        "source": r["source"],
                    }
                )
    except Exception:
        pass
    return results


def render_market_positioning_map(
    df_trend, target, competitors, sentiment_val, height=400, title="市場ポジショニング"
):
    """Reusable function to render market positioning map."""
    plot_data = []
    if df_trend is not None:
        vol = df_trend[target].tail(3).mean()
        plot_data.append(
            {
                "Product": target,
                "話題量": vol,
                "好感度": sentiment_val,
                "Type": "Target",
            }
        )
        for c in competitors:
            if c in df_trend.columns:
                c_vol = df_trend[c].tail(3).mean()
                # For competitors, use neutral or simulated sentiment if not analyzed
                plot_data.append(
                    {
                        "Product": c,
                        "話題量": c_vol,
                        "好感度": random.uniform(-0.15, 0.15),
                        "Type": "Competitor",
                    }
                )

    if plot_data:
        df_map = pd.DataFrame(plot_data)
        fig = px.scatter(
            df_map,
            x="話題量",
            y="好感度",
            color="Type",
            text="Product",
            size="話題量",
            range_y=[-1.1, 1.1],
            height=height,
            title=title,
            color_discrete_map={"Target": "#EF553B", "Competitor": "#636EFA"},
            template="plotly_white",
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.update_traces(textposition="top center")
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    else:
        st.info("データ不足のためポジショニングマップを表示できません。")


# --- Main App Logic ---
st.title("📊 AIブランド戦略・評判分析ダッシュボード")
st.markdown("マーケットトレンド、顧客の声、競合動向、財務指標をAIが統合分析します。")

# --- Sidebar ---
with st.sidebar:
    st.header("📌 アプリ情報")
    st.info(
        "このダッシュボードは、Google Trends, DuckDuckGo, Yahoo Finance, および Gemini AI を使用して、多角的なブランド分析を提供します。"
    )
    if "mkt_results" in st.session_state:
        st.success("✅ 分析データ保持中")
        if st.button("キャッシュをクリア"):
            st.session_state.clear()
            st.rerun()

# --- Analysis Configuration (Expander) ---
with st.expander("🛠️ 分析設定 (Analysis Configuration)", expanded=True):
    col_cfg1, col_cfg2 = st.columns([2, 1])
    with col_cfg1:
        target_product = st.text_input(
            "自社商品・ブランド名", value="アサヒ スーパードライ"
        )
        if "competitor_products" not in st.session_state:
            st.session_state["competitor_products"] = (
                "キリン 一番搾り, サントリー プレミアムモルツ"
            )

        competitor_products = st.text_area(
            "競合商品・ブランド名 (カンマ区切り)",
            value=st.session_state["competitor_products"],
        )

        if st.button("✨ AIで競合を自動抽出"):
            api_key_tmp = get_api_key("GOOGLE_API_KEY", "")
            if not api_key_tmp:
                st.error("APIキーが見つかりません。設定を確認してください。")
            else:
                with st.spinner("AIが市場を調査中..."):
                    prompt = f"{target_product} の主要な競合製品を3〜5つ挙げてください。解説は不要です。カンマ区切りのリスト形式（例: 製品A, 製品B, 製品C）で出力してください。"
                    res = call_gemini(api_key_tmp, prompt)
                    if res:
                        st.session_state["competitor_products"] = (
                            res.strip().replace("、", ", ").replace("・", ", ")
                        )
                        st.rerun()

    with col_cfg2:
        api_key = st.text_input(
            "Gemini API Key", type="password", value=get_api_key("GOOGLE_API_KEY", "")
        )
        period_map = {
            "指定なし": None,
            "過去1日": "d",
            "過去1週間": "w",
            "過去1ヶ月": "m",
        }
        analysis_period = st.selectbox("検索期間 (Web評判)", list(period_map.keys()))
        time_limit = period_map[analysis_period]

# --- Unified Run Button ---
if st.button(
    "🚀 分析を開始する (Start Analysis)", use_container_width=True, type="primary"
):
    if not api_key:
        st.warning("APIキーを入力してください。")
    else:
        with st.status("📊 市場データを収集中...", expanded=True) as status:
            st.write("Google Trends からトレンドデータを取得中...")
            competitors = [
                c.strip() for c in competitor_products.split(",") if c.strip()
            ]
            all_keywords = [target_product] + competitors
            df_trend, df_region, related = get_google_trends(all_keywords)

            st.write("Web上の評判を収集中...")
            opinions = search_opinions(target_product, time_limit=time_limit)

            st.write("AIによるセンチメント分析を実行中...")
            text_blob = "\n".join(
                [f"Title: {o['title']}\nSnippet: {o['snippet']}" for o in opinions]
            )
            prompt = f"""以下の商品評判データを分析し、マーケティング戦略に直結する洞察を抽出してください。
            対象: {target_product}
            データ: {text_blob}
            出力形式(JSON):
            {{
                "sentiment_score": 0.0,
                "sentiment_label": "Positive/Neutral/Negative",
                "summary": "要約(100字)",
                "key_positives": ["強み1", "強み2"],
                "key_negatives": ["弱み1", "弱み2"],
                "improvement_actions": ["施策1", "施策2"]
            }}"""
            result_text = call_gemini(api_key, prompt)

            ai_sentiment = {}
            try:
                clean_json = result_text.strip()
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0]
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0]
                ai_sentiment = json.loads(clean_json)
            except Exception:
                pass

            st.write("最新ニュース・時系列分析を実行中...")
            news_data = search_latest_news(target_product, max_results=15)
            ts_data = []
            if news_data:
                news_blob = "\n".join(
                    [f"Date: {n['published']}, Title: {n['title']}" for n in news_data]
                )
                prompt_ts = f"以下のニュースのセンチメントを日次で抽出してください。JSON形式: [{{'date': 'YYYY-MM-DD', 'score': 0.5, 'title': '...'}}]\n{news_blob}"
                ts_res = call_gemini(api_key, prompt_ts)
                try:
                    clean_ts = ts_res.strip()
                    if "```json" in clean_ts:
                        clean_ts = clean_ts.split("```json")[1].split("```")[0]
                    ts_data = json.loads(clean_ts)
                except Exception:
                    pass

            # --- Generate AI Insights ---
            st.write("AIインサイトを生成中...")
            insights = {}

            # Trend Insight
            if df_trend is not None:
                vol_now = df_trend[target_product].iloc[-1]
                vol_avg = df_trend[target_product].mean()
                trend_direction = "増加" if vol_now > vol_avg else "減少・停滞"
                summary = f"対象ブランド '{target_product}' の12ヶ月のトレンド。最新値は {vol_now:.1f}、平均は {vol_avg:.1f}。現在は{trend_direction}傾向。"
                insights["trend"] = generate_insight(
                    api_key, "マーケットトレンド分析", summary
                )

            # Positioning Insight
            if df_trend is not None:
                sentiment_val = ai_sentiment.get("sentiment_score", 0)
                comp_names = ", ".join(competitors)
                summary = f"対象 '{target_product}' vs 競合 '{comp_names}'。対象の最新話題量は {df_trend[target_product].iloc[-1]:.1f}、好感度スコアは {sentiment_val:.2f}。"
                insights["positioning"] = generate_insight(
                    api_key, "市場ポジショニング分析", summary
                )

            # Sentiment Insight
            if ai_sentiment:
                label = ai_sentiment.get("sentiment_label", "不明")
                score = ai_sentiment.get("sentiment_score", 0)
                summary = f"Web評判の要約: {ai_sentiment.get('summary')}。感情ラベル: {label}、スコア: {score:.2f}。"
                insights["sentiment"] = generate_insight(
                    api_key, "ブランド評判・感情分析", summary
                )

            st.session_state["mkt_results"] = {
                "target": target_product,
                "competitors": competitors,
                "trend": df_trend,
                "region": df_region,
                "related": related,
                "opinions": opinions,
                "ai_sentiment": ai_sentiment,
                "ts_data": ts_data,
                "news_data": news_data,
                "insights": insights,
            }
            status.update(label="✅ 分析完了!", state="complete", expanded=False)

# --- Main Dashboard Tabs ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "📊 総合サマリー",
        "📈 トレンド詳細",
        "🗣️ 評判・AI分析",
        "⚔️ 競合マップ",
        "🏦 財務・マクロ",
    ]
)

if "mkt_results" not in st.session_state:
    st.info("👆 上記の設定を確認し、「分析を開始する」ボタンを押してください。")
else:
    res = st.session_state["mkt_results"]
    insights = res.get("insights", {})

    with tab1:
        st.subheader("🏁 ブランド・エグゼクティブ・サマリー")

        # 1. Scorecard
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        sentiment_val = res["ai_sentiment"].get("sentiment_score", 0)

        with col_m1:
            st.metric(
                "感情スコア (Sentiment)",
                f"{sentiment_val:.2f}",
                delta="Positive" if sentiment_val > 0 else "Negative",
            )
        with col_m2:
            current_vol = (
                res["trend"][res["target"]].iloc[-1] if res["trend"] is not None else 0
            )
            st.metric("最新話題量 (Trend)", f"{int(current_vol)}")
        with col_m3:
            st.metric("Web収集件数", f"{len(res['opinions'])}")
        with col_m4:
            st.metric("主要競合数", f"{len(res['competitors'])}")

        st.markdown("---")

        # 2. Key Plots Side-by-Side (Condensed)
        col_p1, col_p2 = st.columns([3, 2])
        with col_p1:
            if res["trend"] is not None:
                fig_trend_mini = px.line(
                    res["trend"],
                    title="関心度の推移 (12ヶ月)",
                    height=350,
                    template="plotly_white",
                )
                fig_trend_mini.update_layout(
                    legend={
                        "orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1
                    }
                )
                st.plotly_chart(
                    fig_trend_mini, use_container_width=True, config=PLOTLY_CONFIG
                )
                if "trend" in insights:
                    st.info(f"**💡 AI分析インサイト**\n\n{insights['trend']}")
        with col_p2:
            render_market_positioning_map(
                res["trend"],
                res["target"],
                res["competitors"],
                sentiment_val,
                height=350,
            )
            if "positioning" in insights:
                st.success(f"**💡 AI分析インサイト**\n\n{insights['positioning']}")

        st.markdown("---")

        # 3. AI Insights
        st.subheader("💡 AI戦略インサイト")
        ai = res["ai_sentiment"]
        if ai:
            st.info(f"**市場要約**: {ai.get('summary')}")
            col_in1, col_in2 = st.columns(2)
            with col_in1:
                st.success("👍 **主要な評価点 (Strengths)**")
                for p in ai.get("key_positives", []):
                    st.write(f"- {p}")
            with col_in2:
                st.error("👎 **主要な懸念点 (Weaknesses)**")
                for n in ai.get("key_negatives", []):
                    st.write(f"- {n}")

            st.warning(
                f"**推奨アクション**: {', '.join(ai.get('improvement_actions', []))}"
            )
        else:
            st.write("AI分析データがありません。")

    with tab2:
        st.subheader("📈 トレンド深掘り")
        if res["trend"] is not None:
            fig_trend_full = px.line(
                res["trend"], title="話題量詳細 (時系列)", template="plotly_white"
            )
            st.plotly_chart(
                fig_trend_full, use_container_width=True, config=PLOTLY_CONFIG
            )
            if "trend" in insights:
                st.info(f"**💡 AI分析インサイト**\n\n{insights['trend']}")

            c_g1, c_g2 = st.columns(2)
            with c_g1:
                st.subheader("🗺️ 地域別関心")
                df_reg = res["region"].sort_values(res["target"]).tail(10)
                fig_reg = px.bar(
                    df_reg, x=res["target"], orientation="h", title="都道府県別関心度"
                )
                st.plotly_chart(fig_reg, use_container_width=True, config=PLOTLY_CONFIG)
            with c_g2:
                st.subheader("🔍 関連キーワード")
                rel = res["related"]
                if rel and res["target"] in rel:
                    rising = rel[res["target"]].get("rising")
                    if rising is not None and not rising.empty:
                        st.dataframe(rising.head(10), use_container_width=True)
                    else:
                        st.info("急上昇ワードなし")
        else:
            st.info("トレンドデータが取得できませんでした。")

    with tab3:
        st.subheader("🗣️ 評判・センチメント詳細")
        col_s1, col_s2 = st.columns([1, 2])
        with col_s1:
            score = res["ai_sentiment"].get("sentiment_score", 0)
            fig_gauge = go.Figure(
                go.Indicator(
                    mode="gauge+number",
                    value=score,
                    title={"text": "好感度ゲージ"},
                    gauge={
                        "axis": {"range": [-1, 1]},
                        "bar": {"color": "#003366"},
                        "steps": [
                            {"range": [-1, -0.3], "color": "#FFCCCC"},
                            {"range": [0.3, 1], "color": "#CCFFCC"},
                        ],
                    },
                )
            )
            fig_gauge.update_layout(height=350)
            st.plotly_chart(fig_gauge, use_container_width=True, config=PLOTLY_CONFIG)

        with col_s2:
            if res["ts_data"]:
                df_ts = pd.DataFrame(res["ts_data"])
                df_ts["date"] = pd.to_datetime(df_ts["date"])
                df_ts = df_ts.sort_values("date")
                fig_ts = px.line(
                    df_ts,
                    x="date",
                    y="score",
                    markers=True,
                    title="ニュース・センチメント推移",
                    template="plotly_white",
                )
                fig_ts.add_hline(y=0, line_dash="dash", line_color="gray")
                st.plotly_chart(fig_ts, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                st.info("時系列データが不足しています。")

        if "sentiment" in insights:
            st.success(f"**💡 AI分析インサイト**\n\n{insights['sentiment']}")

        with st.expander("収集されたWebの声・ソース (Raw Data)"):
            for op in res["opinions"]:
                st.markdown(
                    f"- **{op['title']}** ([Link]({op['link']})) - {op['source']}"
                )

    with tab4:
        st.subheader("⚔️ 競合分析・ポジショニング")
        st.markdown(
            "話題量（関心）と好感度（質）を軸にした市場マップです。競合抽出は上部の「分析設定」で行えます。"
        )
        render_market_positioning_map(
            res["trend"],
            res["target"],
            res["competitors"],
            sentiment_val,
            height=550,
            title="詳細市場ポジショニングマップ",
        )
        if "positioning" in insights:
            st.success(f"**💡 AI分析インサイト**\n\n{insights['positioning']}")

    with tab5:
        st.subheader("🏦 財務・マクロ指標相関")
        st.markdown("Google Trendsと金融指標（株価・為替等）の相関を可視化します。")
        c_f1, c_f2 = st.columns(2)
        with c_f1:
            ticker1 = st.text_input(
                "株価ティッカー (Yahoo Finance形式)", value="7203.T"
            )
        with c_f2:
            ticker2 = st.text_input("比較指標ティッカー (為替等)", value="JPY=X")

        if st.button("財務相関分析を実行", use_container_width=True):
            with st.spinner("財務データを取得中..."):
                try:
                    s1_df = yf.download(ticker1, period="1y")
                    s2_df = yf.download(ticker2, period="1y")

                    if not s1_df.empty and not s2_df.empty:
                        s1 = s1_df["Close"].squeeze()
                        s2 = s2_df["Close"].squeeze()

                        if (
                            res["trend"] is not None
                            and res["target"] in res["trend"].columns
                        ):
                            trends = res["trend"][res["target"]]

                            s1.name = ticker1
                            s2.name = ticker2
                            trends.name = "Trend"

                            def norm(s):
                                if s.max() == s.min():
                                    return s * 0
                                return (s - s.min()) / (s.max() - s.min())

                            combined = (
                                pd.concat([trends, s1, s2], axis=1).ffill().dropna()
                            )

                            if not combined.empty:
                                norm_df = combined.apply(norm)
                                fig_fin = px.line(
                                    norm_df,
                                    title=f"正規化比較チャート: {res['target']} vs {ticker1} & {ticker2}",
                                    template="plotly_white",
                                )
                                st.plotly_chart(
                                    fig_fin,
                                    use_container_width=True,
                                    config=PLOTLY_CONFIG,
                                )

                                corr1 = norm_df.corr()["Trend"][ticker1]
                                corr2 = norm_df.corr()["Trend"][ticker2]
                                col_c1, col_c2 = st.columns(2)
                                col_c1.metric(
                                    f"トレンド vs {ticker1} 相関係数", f"{corr1:.2f}"
                                )
                                col_c2.metric(
                                    f"トレンド vs {ticker2} 相関係数", f"{corr2:.2f}"
                                )

                                # --- Generate Financial Insight ---
                                summary_fin = f"ブランドトレンド vs {ticker1} (相関係数: {corr1:.2f})、ブランドトレンド vs {ticker2} (相関係数: {corr2:.2f})。"
                                fin_insight = generate_insight(
                                    api_key, "財務・マクロ相関分析", summary_fin
                                )
                                st.session_state["mkt_results"]["insights"][
                                    "financial"
                                ] = fin_insight
                                st.rerun()
                            else:
                                st.error("共通の分析期間が見つかりませんでした。")
                        else:
                            st.error("トレンドデータが不足しています。")
                    else:
                        st.error(
                            "ティッカー情報の取得に失敗しました。入力内容を確認してください。"
                        )
                except Exception as e:
                    st.error(f"分析実行エラー: {e}")

        # Display Financial Insight if it exists in state
        if "financial" in insights:
            st.info(f"**💡 AI分析インサイト**\n\n{insights['financial']}")
