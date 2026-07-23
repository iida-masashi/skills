import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from consultant_toolkit.ui_components.ui_helpers import color_by_sign


def render_capex_analysis(
    target_ticker,
    target_company_name,
    load_financial_data,
    get_val_safe,
):
    """
    サブタブ 3.3: 投資効率: CAPEX vs Depreciation (フリーキャッシュフロー分析)
    """
    st.header("3.3 投資効率: CAPEX vs Depreciation (フリーキャッシュフロー分析)")
    st.markdown(
        "EV化に向けて巨額の設備投資（CAPEX）が求められる業界において、**「減価償却費を超えた過剰投資の有無（FCF枯渇の可能性）」**のトレンドを分析します。"
    )

    @st.cache_data(ttl=3600)  # Cache for 1 hour
    def get_capex_analysis_data(target_ticker_symbol):
        import yfinance as yf

        cf_data_raw = yf.Ticker(target_ticker_symbol).cash_flow
        income_statement_raw, _ = load_financial_data(target_ticker_symbol)

        cf_data = []
        years = cf_data_raw.columns.sort_values()
        for y in years:
            # CAPEX is usually negative in cash flow statements
            capex_raw = get_val_safe(
                cf_data_raw, ["Capital Expenditure", "Capital Expenditures"], y
            )
            capex = abs(capex_raw) if capex_raw != 0 else 0

            dep = get_val_safe(
                cf_data_raw, ["Depreciation And Amortization", "Depreciation"], y
            )

            ocf = get_val_safe(
                cf_data_raw,
                [
                    "Operating Cash Flow",
                    "Total Cash From Operating Activities",
                    "Cash Flow From Continuing Operating Activities",
                ],
                y,
            )
            fcf = get_val_safe(cf_data_raw, ["Free Cash Flow"], y)
            if fcf == 0 and ocf != 0:
                fcf = ocf - capex

            rev = get_val_safe(
                income_statement_raw, ["Total Revenue", "Operating Revenue"], y
            )

            if ocf != 0 or capex != 0:
                # KPI計算
                capex_coverage = capex / dep if dep > 0 else 0
                reinvestment_rate = capex / ocf if ocf > 0 else 0
                fcf_margin = fcf / rev if rev > 0 else 0

                cf_data.append(
                    {
                        "Year": str(y.date())[:4],
                        "CAPEX (設備投資)": capex / 1e6,
                        "Depreciation (減価償却費)": dep / 1e6,
                        "OCF (営業CF)": ocf / 1e6,
                        "FCF (フリーCF)": fcf / 1e6,
                        "Revenue": rev / 1e6,
                        "CAPEX Coverage Ratio": capex_coverage,
                        "Reinvestment Rate": reinvestment_rate,
                        "FCF Margin": fcf_margin,
                    }
                )

        return (
            pd.DataFrame(cf_data).sort_values("Year") if cf_data else pd.DataFrame()
        )

    try:
        df_cf = get_capex_analysis_data(target_ticker)

        if not df_cf.empty:
            # --- セクション1: 絶対額分析 ---
            col_f1, col_f2 = st.columns([2, 1])
            with col_f1:
                fig_cf = go.Figure()
                fig_cf.add_trace(
                    go.Bar(
                        name="CAPEX (支出・マイナス要因)",
                        x=df_cf["Year"],
                        y=-df_cf["CAPEX (設備投資)"],
                        marker_color="#d62728",
                    )
                )
                fig_cf.add_trace(
                    go.Bar(
                        name="Depreciation (費用・非資金)",
                        x=df_cf["Year"],
                        y=df_cf["Depreciation (減価償却費)"],
                        marker_color="#1f77b4",
                    )
                )

                fig_cf.update_layout(
                    title=f"{target_company_name}: 設備投資(CAPEX) vs 減価償却費 (単位: 百万円)",
                    barmode="group",
                    yaxis_title="百万円",
                    template="plotly_white",
                    legend={
                        "orientation": "h",
                        "yanchor": "bottom",
                        "y": 1.02,
                        "xanchor": "right",
                        "x": 1,
                    },
                )
                st.plotly_chart(fig_cf, use_container_width=True)

            with col_f2:
                fig_fcf = go.Figure()
                fig_fcf.add_trace(
                    go.Bar(
                        name="FCF",
                        x=df_cf["Year"],
                        y=df_cf["FCF (フリーCF)"],
                        marker_color=df_cf["FCF (フリーCF)"].apply(
                            color_by_sign
                        ),
                    )
                )
                fig_fcf.add_trace(
                    go.Scatter(
                        name="OCF",
                        x=df_cf["Year"],
                        y=df_cf["OCF (営業CF)"],
                        mode="lines+markers",
                        marker_color="blue",
                    )
                )
                fig_fcf.update_layout(
                    title="キャッシュ創出力 (OCF & FCF)",
                    yaxis_title="百万円",
                    template="plotly_white",
                    showlegend=False,
                )
                st.plotly_chart(fig_fcf, use_container_width=True)

            # --- セクション2: 効率性KPI分析 ---
            st.divider()
            st.subheader("📊 投資効率性指標 (Investment Efficiency KPIs)")

            col_k1, col_k2 = st.columns(2)

            with col_k1:
                # CAPEX Coverage Ratio & Reinvestment Rate
                fig_eff = go.Figure()
                fig_eff.add_trace(
                    go.Scatter(
                        name="CAPEX Coverage (CAPEX/Dep)",
                        x=df_cf["Year"],
                        y=df_cf["CAPEX Coverage Ratio"],
                        mode="lines+markers",
                        line={"color": "#e00078", "width": 3},
                    )
                )
                fig_eff.add_trace(
                    go.Scatter(
                        name="Reinvestment Rate (CAPEX/OCF)",
                        x=df_cf["Year"],
                        y=df_cf["Reinvestment Rate"],
                        mode="lines+markers",
                        line={"color": "#00aedb", "dash": "dot"},
                    )
                )

                fig_eff.add_hline(
                    y=1.0,
                    line_dash="dash",
                    line_color="gray",
                    annotation_text="償却費と同額投資 (維持)",
                )

                fig_eff.update_layout(
                    title="投資の積極性 (CAPEX Coverage Ratio)",
                    yaxis_title="倍率 (x)",
                    template="plotly_white",
                    legend={"orientation": "h", "y": 1.1},
                )
                st.plotly_chart(fig_eff, use_container_width=True)

            with col_k2:
                # FCF Margin
                fig_margin = go.Figure()
                fig_margin.add_trace(
                    go.Bar(
                        name="FCF Margin (%)",
                        x=df_cf["Year"],
                        y=df_cf["FCF Margin"] * 100,
                        marker_color=df_cf["FCF Margin"].apply(
                            color_by_sign
                        ),
                    )
                )

                fig_margin.update_layout(
                    title="売上高FCFマージン (稼ぐ力)",
                    yaxis_title="%",
                    template="plotly_white",
                )
                st.plotly_chart(fig_margin, use_container_width=True)

            st.info(
                "💡 **分析上のポイント:**\n「CAPEX Coverage Ratio（ピンク線）」が1.0を恒常的に超えている場合、会社は事業拡大フェーズにあります。ただし、同時に「FCF Margin（右グラフ）」がマイナスまたは低水準で推移しているのであれば、**「利益なき繁忙（過剰投資）」**の兆候です。投資が将来のOCF増加に確実に繋がっているかどうかを定量的に検証してください。"
            )
    except (ConnectionError, KeyError, ValueError, OSError) as e:
        st.error(f"キャッシュフロー・CAPEXデータの取得に失敗しました: {e}")
