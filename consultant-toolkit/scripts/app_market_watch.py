
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# Import utility modules
from consultant_toolkit.env_loader import get_api_key, load_environment
from prophet import Prophet
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import BollingerBands

# --- Page Config ---
st.set_page_config(page_title="AIマーケット・アナリスト", page_icon="🌏", layout="wide")


# --- CSS Injection (Mobile Optimization) ---
def local_css(content: str):
    st.markdown(f"<style>{content}</style>", unsafe_allow_html=True)


local_css("""
    @media screen and (max-width: 768px) {
        div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
    }
""")


# --- Helper Functions ---
load_environment()


@st.cache_data(ttl=3600)
def make_forecast(ticker_symbol, periods=180):
    """Generate forecast using Prophet for a specific ticker."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="5y")
        df = df.reset_index()
        # Ensure timezone naive
        df["Date"] = df["Date"].dt.tz_localize(None)

        df_prophet = df[["Date", "Close"]].rename(columns={"Date": "ds", "Close": "y"})

        m = Prophet(
            daily_seasonality=False, weekly_seasonality=False, yearly_seasonality=True
        )
        m.fit(df_prophet)

        future = m.make_future_dataframe(periods=periods)
        forecast = m.predict(future)

        return df, forecast
    except Exception:
        return None, None


@st.cache_data(ttl=300)  # Cache for 5 mins
def get_market_data():
    """Fetch global market data."""
    tickers = {
        # Indices
        "S&P 500": "^GSPC",
        "Nasdaq 100": "^IXIC",
        "Nikkei 225": "^N225",
        "Euro Stoxx 50": "^STOXX50E",
        "Shanghai Comp": "000001.SS",
        # FX
        "USD/JPY": "JPY=X",
        "EUR/USD": "EURUSD=X",
        # Commodities
        "Gold": "GC=F",
        "Crude Oil (WTI)": "CL=F",
        "Bitcoin": "BTC-USD",
        # US Sectors (ETF)
        "Tech (XLK)": "XLK",
        "Finance (XLF)": "XLF",
        "Energy (XLE)": "XLE",
        "Healthcare (XLV)": "XLV",
    }

    data = []
    for name, ticker in tickers.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1mo")
            if len(hist) > 1:
                current = hist["Close"].iloc[-1]
                prev_day = hist["Close"].iloc[-2]
                prev_week = hist["Close"].iloc[-5] if len(hist) >= 5 else current
                prev_month = hist["Close"].iloc[0]

                change_1d = ((current - prev_day) / prev_day) * 100
                change_1w = ((current - prev_week) / prev_week) * 100
                change_1m = ((current - prev_month) / prev_month) * 100

                # Category
                if "^" in ticker or "000001" in ticker:
                    category = "Index"
                elif "=X" in ticker:
                    category = "FX"
                elif "=F" in ticker or "BTC" in ticker:
                    category = "Commodity/Crypto"
                else:
                    category = "Sector"

                data.append(
                    {
                        "Name": name,
                        "Symbol": ticker,
                        "Category": category,
                        "Price": current,
                        "1D %": change_1d,
                        "1W %": change_1w,
                        "1M %": change_1m,
                    }
                )
        except Exception:
            pass

    return pd.DataFrame(data)


@st.cache_data(ttl=3600)
def get_technical_data(ticker_symbol):
    """Fetch and calculate technical indicators."""
    ticker = yf.Ticker(ticker_symbol)
    df = ticker.history(period="1y")

    if df.empty:
        return None

    # Indicators
    df["SMA_50"] = SMAIndicator(df["Close"], window=50).sma_indicator()
    df["SMA_200"] = SMAIndicator(df["Close"], window=200).sma_indicator()
    df["RSI"] = RSIIndicator(df["Close"]).rsi()

    bb = BollingerBands(df["Close"])
    df["BB_High"] = bb.bollinger_hband()
    df["BB_Low"] = bb.bollinger_lband()

    macd = MACD(df["Close"])
    df["MACD"] = macd.macd()
    df["MACD_Signal"] = macd.macd_signal()

    return df


@st.cache_data(ttl=3600)
def get_sector_history():
    """Fetch 1-year history for all US Sector ETFs."""
    sectors = {
        "Technology": "XLK",
        "Financials": "XLF",
        "Healthcare": "XLV",
        "Energy": "XLE",
        "Cons. Staples": "XLP",
        "Cons. Discret.": "XLY",
        "Industrials": "XLI",
        "Materials": "XLB",
        "Real Estate": "XLRE",
        "Communication": "XLC",
        "Utilities": "XLU",
        "S&P 500": "SPY",  # Benchmark
    }

    data = {}
    for name, ticker in sectors.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y")
            if not hist.empty:
                data[name] = hist["Close"]
        except Exception as e:
            st.warning(f"Failed to fetch data for {name}: {e}")
            pass

    return pd.DataFrame(data)


# --- Sidebar ---
st.sidebar.title("🌏 AIマーケット・アナリスト")
api_key = st.sidebar.text_input(
    "Gemini API Key", type="password", value=get_api_key("GOOGLE_API_KEY", "")
)

target_index = st.sidebar.selectbox(
    "詳細分析対象",
    ["^N225", "^GSPC", "^IXIC", "JPY=X", "BTC-USD"],
    key="target_index_select",
)

# --- Main Content ---
st.title("🌏 Global Market Dashboard")

# Tab Structure
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "📊 マーケット・ヒートマップ",
        "📈 テクニカル & AI分析",
        "🏭 セクター・ローテーション",
        "🌾 コモディティ AI予測",
        "💱 コモディティ円換算シミュレーター",
    ]
)

with tab1:
    st.subheader("世界の市場動向 (Heatmap)")
    df_market = get_market_data()

    if not df_market.empty:
        # Heatmap (Treemap)
        fig_map = px.treemap(
            df_market,
            path=[px.Constant("World"), "Category", "Name"],
            values="Price",  # Dummy size, ideally Market Cap but hard to get for indices/FX
            color="1D %",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            title="本日の市場ヒートマップ (色は前日比%)",
        )
        st.plotly_chart(fig_map, use_container_width=True)

        # Table
        st.dataframe(
            df_market.style.format(
                {
                    "Price": "{:,.2f}",
                    "1D %": "{:+.2f}%",
                    "1W %": "{:+.2f}%",
                    "1M %": "{:+.2f}%",
                }
            ).background_gradient(
                cmap="RdYlGn", subset=["1D %", "1W %", "1M %"], vmin=-3, vmax=3
            )
        )
    else:
        st.error("データ取得に失敗しました。")

with tab2:
    st.subheader(f"📈 テクニカル分析: {target_index}")

    # Force reload if changed? No, cache relies on args.
    df_tech = get_technical_data(target_index)

    if df_tech is not None and not df_tech.empty:
        # Chart
        fig_tech = go.Figure()
        fig_tech.add_trace(
            go.Scatter(x=df_tech.index, y=df_tech["Close"], name="Close")
        )
        fig_tech.add_trace(
            go.Scatter(
                x=df_tech.index,
                y=df_tech["SMA_50"],
                name="SMA 50",
                line={"color": "orange"},
            )
        )
        fig_tech.add_trace(
            go.Scatter(
                x=df_tech.index,
                y=df_tech["SMA_200"],
                name="SMA 200",
                line={"color": "blue"},
            )
        )
        fig_tech.add_trace(
            go.Scatter(
                x=df_tech.index,
                y=df_tech["BB_High"],
                name="BB High",
                line={"color": "gray", "dash": "dot"},
            )
        )
        fig_tech.add_trace(
            go.Scatter(
                x=df_tech.index,
                y=df_tech["BB_Low"],
                name="BB Low",
                line={"color": "gray", "dash": "dot"},
            )
        )

        fig_tech.update_layout(
            title=f"{target_index} Price & Indicators",
            xaxis_title="Date",
            yaxis_title="Price",
        )
        st.plotly_chart(fig_tech, use_container_width=True)

        # Sub-charts (RSI, MACD)
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            fig_rsi = px.line(
                df_tech, x=df_tech.index, y="RSI", title="RSI (Relative Strength Index)"
            )
            fig_rsi.add_hline(y=70, line_dash="dash", line_color="red")
            fig_rsi.add_hline(y=30, line_dash="dash", line_color="green")
            st.plotly_chart(fig_rsi, use_container_width=True)

        with col_t2:
            fig_macd = go.Figure()
            fig_macd.add_trace(
                go.Scatter(x=df_tech.index, y=df_tech["MACD"], name="MACD")
            )
            fig_macd.add_trace(
                go.Scatter(x=df_tech.index, y=df_tech["MACD_Signal"], name="Signal")
            )
            fig_macd.update_layout(title="MACD Trend")
            st.plotly_chart(fig_macd, use_container_width=True)

        # AI Analysis
        st.markdown("---")
        st.subheader("🤖 AI相場解説")
        if api_key:
            if st.button("AIにチャートを診断させる"):
                latest = df_tech.iloc[-1]
                prompt_tech = f"""
                あなたはプロのテクニカルアナリストです。以下の指標に基づいて、現在の{target_index}の相場状況を診断してください。

                現在値: {latest["Close"]:.2f}
                SMA 50: {latest["SMA_50"]:.2f}
                SMA 200: {latest["SMA_200"]:.2f} (ゴールデンクロス/デッドクロスの可能性は？)
                RSI (14): {latest["RSI"]:.2f} (買われすぎ70/売られすぎ30)
                MACD: {latest["MACD"]:.2f} / Signal: {latest["MACD_Signal"]:.2f}
                ボリンジャーバンド: High {latest["BB_High"]:.2f} / Low {latest["BB_Low"]:.2f}

                出力形式:
                1. **トレンド判定**: (上昇/下降/レンジ)
                2. **注目ポイント**: (RSIの過熱感、MACDの転換点など)
                3. **短期的な見通し**: (強気/弱気/様子見)

                ※投資助言ではありません。客観的なテクニカル分析に徹してください。
                """
                with st.spinner("AIがチャートを凝視しています..."):
                    try:
                        from consultant_toolkit.gemini_client import DEFAULT_MODEL, create_gemini_client

                        client = create_gemini_client(api_key=api_key)
                        response = client.models.generate_content(
                            model=DEFAULT_MODEL, contents=prompt_tech
                        )
                        st.markdown(response.text)
                    except Exception as e:
                        st.error(f"AI分析エラー: {e}")
        else:
            st.warning("AI分析にはAPI Keyが必要です。")
    else:
        st.error(f"データ取得に失敗しました: {target_index}")

with tab3:
    st.subheader("🏭 高度なセクター・ローテーション分析")

    with st.spinner("セクターデータを取得・計算中..."):
        df_sectors = get_sector_history()

    if not df_sectors.empty and "S&P 500" in df_sectors.columns:
        # 1. Normalized Trend
        st.markdown("#### 📈 セクター別パフォーマンス比較 (1年 = 100)")
        df_norm = df_sectors / df_sectors.iloc[0] * 100
        fig_trend = px.line(
            df_norm, x=df_norm.index, y=df_norm.columns, title="相対パフォーマンス推移"
        )
        st.plotly_chart(fig_trend, use_container_width=True)

        col_s1, col_s2 = st.columns(2)

        # 2. RRG-style Map
        with col_s1:
            st.markdown("#### 🔄 景気サイクルマップ (RRG風)")
            st.caption(
                "各セクターの「相対的な強さ」と「勢い」を可視化。右上が「主導 (Leading)」、左下が「出遅れ (Lagging)」です。"
            )

            # Calculate RRG proxies
            rrg_data = []
            spy = df_sectors["S&P 500"]

            for col in df_sectors.columns:
                if col == "S&P 500":
                    continue

                # Relative Strength (RS)
                rs = df_sectors[col] / spy

                # RS-Ratio (Trend): Distance from 50-day SMA of RS
                rs_sma = rs.rolling(window=50).mean()
                rs_ratio = ((rs.iloc[-1] - rs_sma.iloc[-1]) / rs_sma.iloc[-1]) * 100

                # RS-Momentum: Rate of Change of RS (10-day)
                rs_mom = ((rs.iloc[-1] - rs.iloc[-10]) / rs.iloc[-10]) * 100

                rrg_data.append(
                    {
                        "Sector": col,
                        "RS-Ratio (Trend)": rs_ratio,
                        "RS-Momentum (Velocity)": rs_mom,
                        "Size": 20,  # Fixed size
                    }
                )

            df_rrg = pd.DataFrame(rrg_data)

            fig_rrg = px.scatter(
                df_rrg,
                x="RS-Ratio (Trend)",
                y="RS-Momentum (Velocity)",
                color="Sector",
                text="Sector",
                size="Size",
                title="セクター相対回転グラフ (vs S&P 500)",
                template="plotly_white",
            )
            # Add quadrants
            fig_rrg.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_rrg.add_vline(x=0, line_dash="dash", line_color="gray")

            # Add quadrant labels
            fig_rrg.add_annotation(
                x=2,
                y=2,
                text="LEADING (主導)",
                showarrow=False,
                font={"color": "green"},
            )
            fig_rrg.add_annotation(
                x=-2,
                y=2,
                text="IMPROVING (回復)",
                showarrow=False,
                font={"color": "blue"},
            )
            fig_rrg.add_annotation(
                x=-2,
                y=-2,
                text="LAGGING (出遅れ)",
                showarrow=False,
                font={"color": "red"},
            )
            fig_rrg.add_annotation(
                x=2,
                y=-2,
                text="WEAKENING (減速)",
                showarrow=False,
                font={"color": "orange"},
            )

            fig_rrg.update_traces(textposition="top center")
            st.plotly_chart(fig_rrg, use_container_width=True)

        # 3. Correlation Heatmap
        with col_s2:
            st.markdown("#### 🔥 相関ヒートマップ (直近3ヶ月)")
            st.caption(
                "セクター間の連動性を確認。赤色が濃いほど強い正の相関（一緒に動く）があります。"
            )

            # Correlation of returns
            df_returns = df_sectors.pct_change().tail(
                60
            )  # Last 3 months (approx 60 trading days)
            corr_matrix = df_returns.corr()

            fig_corr = px.imshow(
                corr_matrix,
                text_auto=".2f",
                aspect="auto",
                color_continuous_scale="RdBu_r",
                zmin=-1,
                zmax=1,
                title="セクター間相関行列",
            )
            st.plotly_chart(fig_corr, use_container_width=True)

    else:
        st.error("セクターデータの取得に失敗しました。")

with tab4:
    st.subheader("🌾 コモディティ価格予測 (USD建て)")
    st.caption(
        "Prophet (AI) を用いて、主要コモディティの向こう半年の価格トレンドを予測します。"
    )

    # Constants
    COMMODITIES = {
        # 貴金属
        "金 (Gold)": "GC=F",
        "銀 (Silver)": "SI=F",
        "プラチナ (Platinum)": "PL=F",
        "パラジウム (Palladium)": "PA=F",
        # エネルギー
        "原油 (WTI Crude Oil)": "CL=F",
        "天然ガス (Natural Gas)": "NG=F",
        # 産業用金属
        "銅 (Copper)": "HG=F",
        "アルミニウム (Aluminum)": "ALI=F",
        # バッテリー・レアメタル (ETF代用)
        "リチウム (Lithium ETF)": "LIT",
        "レアアース (Rare Earth ETF)": "REMX",
        # 農産物
        "小麦 (Wheat)": "ZW=F",
        "砂糖 (Sugar #11)": "SB=F",
        "大豆 (Soybean)": "ZS=F",
        "トウモロコシ (Corn)": "ZC=F",
        "コーヒー (Coffee)": "KC=F",
    }

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        selected_comm = st.selectbox(
            "分析対象を選択", list(COMMODITIES.keys()), key="comm_select"
        )
    with col_c2:
        forecast_months = st.slider("予測期間 (月)", 1, 12, 6, key="comm_months")
        forecast_days = forecast_months * 30

    target_ticker_comm = COMMODITIES[selected_comm]

    if st.button("予測を実行 🚀", key="btn_comm_forecast"):
        with st.spinner(f"{selected_comm} の未来を計算中..."):
            # 1. Commodity Forecast
            df_comm, fc_comm = make_forecast(target_ticker_comm, periods=forecast_days)

            # 2. FX Forecast (USD/JPY)
            df_fx, fc_fx = make_forecast("JPY=X", periods=forecast_days)

            if fc_comm is not None and fc_fx is not None:
                # Store results in Session State
                st.session_state["comm_data"] = {
                    "name": selected_comm,
                    "df_comm": df_comm,
                    "fc_comm": fc_comm,
                    "fc_fx": fc_fx,
                    "months": forecast_months,
                }
            else:
                st.error("データの取得または予測に失敗しました。")

    # Display Result if available
    if "comm_data" in st.session_state:
        data = st.session_state["comm_data"]
        # Check if selected commodity matches cached data (optional warning)
        if data["name"] != selected_comm:
            st.warning(
                f"表示中のデータは {data['name']} です。再実行ボタンを押すと {selected_comm} に更新されます。"
            )

        fc_comm = data["fc_comm"]
        df_comm = data["df_comm"]

        st.markdown(f"#### 📈 {data['name']} 価格トレンド (USD)")
        latest_price = df_comm["Close"].iloc[-1]
        pred_price = fc_comm["yhat"].iloc[-1]
        change_pct = ((pred_price - latest_price) / latest_price) * 100

        st.metric(
            f"{data['months']}ヶ月後の予測値",
            f"${pred_price:.2f}",
            f"{change_pct:+.2f}%",
        )

        fig_comm = go.Figure()
        fig_comm.add_trace(
            go.Scatter(
                x=df_comm["Date"],
                y=df_comm["Close"],
                name="実績 (History)",
                line={"color": "gray"},
            )
        )
        fig_comm.add_trace(
            go.Scatter(
                x=fc_comm["ds"],
                y=fc_comm["yhat"],
                name="AI予測 (Forecast)",
                line={"color": "blue"},
            )
        )
        fig_comm.add_trace(
            go.Scatter(
                x=pd.concat([fc_comm["ds"], fc_comm["ds"][::-1]]),
                y=pd.concat([fc_comm["yhat_upper"], fc_comm["yhat_lower"][::-1]]),
                fill="toself",
                fillcolor="rgba(0,0,255,0.2)",
                line={"color": "rgba(255,255,255,0)"},
                name="信頼区間",
            )
        )
        st.plotly_chart(fig_comm, use_container_width=True)

with tab5:
    st.subheader("💱 円換算コスト・シミュレーター")

    if "comm_data" in st.session_state:
        data = st.session_state["comm_data"]
        fc_comm = data["fc_comm"]
        fc_fx = data["fc_fx"]

        st.caption(
            f"**{data['name']}** の予測データに基づき、為替リスクを加味した円建てコストを試算します。"
        )

        # Merge Forecasts
        fc_c = fc_comm[["ds", "yhat"]].rename(columns={"yhat": "price"})
        fc_f = fc_fx[["ds", "yhat"]].rename(columns={"yhat": "fx"})
        merged = pd.merge(fc_c, fc_f, on="ds", how="inner")
        merged["yen_price"] = merged["price"] * merged["fx"]

        # Simulation Slider
        fx_adj = st.slider(
            "為替レート調整 (予測に対して)",
            -20.0,
            20.0,
            0.0,
            1.0,
            help="円安/円高シナリオをシミュレーション",
            key="sim_fx_adj",
        )
        merged["yen_price_sim"] = merged["price"] * (merged["fx"] + fx_adj)

        fig_yen = go.Figure()
        fig_yen.add_trace(
            go.Scatter(
                x=merged["ds"],
                y=merged["yen_price"],
                name="AI予測 (円建て)",
                line={"color": "green", "dash": "dot"},
            )
        )
        fig_yen.add_trace(
            go.Scatter(
                x=merged["ds"],
                y=merged["yen_price_sim"],
                name=f"シミュレーション ({fx_adj:+.0f}円)",
                line={"color": "red"},
            )
        )

        fig_yen.update_layout(
            title=f"{data['name']} 円建て予測 (JPY)",
            xaxis_title="Date",
            yaxis_title="Price (JPY)",
        )
        st.plotly_chart(fig_yen, use_container_width=True)

        final_price = merged["yen_price_sim"].iloc[-1]
        st.info(
            f"現在のAI予測と為替シナリオ({fx_adj:+.0f}円)では、{data['months']}ヶ月後の円建て価格は **{final_price:,.0f}円** になると予測されます。"
        )
    else:
        st.info("👈 「🌾 コモディティ AI予測」タブで、まずは予測を実行してください。")
