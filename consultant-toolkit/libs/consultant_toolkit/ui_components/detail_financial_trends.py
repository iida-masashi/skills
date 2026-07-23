import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from consultant_toolkit.ui_components.ui_helpers import color_by_sign


def render_financial_trends(
    target_ticker,
    target_company_name,
    load_financial_data,
    get_val_safe,
    ensure_historical_marginal_profit_data,
    load_marginal_profit_data,
    ANIMATION_DURATION_MS=2500,
    ANIMATION_TRANSITION_MS=1500,
):
    """
    サブタブ 2.1: 📉 財務推移分析 (Revenue & Profit Margin Evolution) のレンダリング
    """
    st.header("2.1 財務推移分析 (Revenue & Profit Margin Evolution)")
    st.markdown(
        "「対象企業の過去財務データから、売上高・利益率・営業利益の推移を可視化します。データが取得できない場合はデモデータ（モック）を表示します。」"
    )

    @st.cache_data(ttl=3600)
    def get_historical_financials(ticker_symbol):
        """過去の財務データを取得してPPM風に可視化"""
        try:
            income_statement, balance_sheet = load_financial_data(ticker_symbol)

            if income_statement.empty:
                return pd.DataFrame(), False

            history_data = []
            years = income_statement.columns.sort_values()

            for year in years:
                revenue = get_val_safe(
                    income_statement, ["Total Revenue", "Operating Revenue"], year
                )
                operating_income = get_val_safe(
                    income_statement, ["Operating Income", "EBIT"], year
                )
                gross_profit = get_val_safe(
                    income_statement, ["Gross Profit"], year
                )

                if revenue > 0:
                    operating_margin = (
                        operating_income / revenue if operating_income != 0 else 0.0
                    )
                    gross_margin = (
                        gross_profit / revenue if gross_profit != 0 else 0.0
                    )

                    history_data.append(
                        {
                            "Year": str(year.date())[:4],
                            "Revenue_M": revenue / 1e6,
                            "Operating_Income_M": operating_income / 1e6,
                            "Operating_Margin": operating_margin,
                            "Gross_Margin": gross_margin,
                        }
                    )

            return pd.DataFrame(history_data), True

        except (ConnectionError, KeyError, ValueError):
            return pd.DataFrame(), False

    df_history, has_real_data = get_historical_financials(target_ticker)

    # 実データがある場合
    if has_real_data and not df_history.empty:
        st.success(f"✅ {target_company_name} の実データを取得しました")

        # 財務推移チャート
        col1, col2 = st.columns(2)

        with col1:
            # 売上高推移
            fig_revenue = go.Figure()
            fig_revenue.add_trace(
                go.Bar(
                    x=df_history["Year"],
                    y=df_history["Revenue_M"],
                    name="売上高",
                    marker_color="#1f77b4",
                )
            )
            fig_revenue.update_layout(
                title=f"{target_company_name} 売上高推移",
                yaxis_title="売上高 (百万円)",
                template="plotly_white",
                height=400,
            )
            st.plotly_chart(fig_revenue, use_container_width=True)

        with col2:
            # 利益率推移
            fig_margin = go.Figure()
            fig_margin.add_trace(
                go.Scatter(
                    x=df_history["Year"],
                    y=df_history["Operating_Margin"] * 100,
                    name="営業利益率",
                    mode="lines+markers",
                    marker_color="#e00078",
                    line={"width": 3},
                )
            )
            fig_margin.add_trace(
                go.Scatter(
                    x=df_history["Year"],
                    y=df_history["Gross_Margin"] * 100,
                    name="売上総利益率",
                    mode="lines+markers",
                    marker_color="#2ca02c",
                    line={"width": 3, "dash": "dot"},
                )
            )
            fig_margin.update_layout(
                title=f"{target_company_name} 利益率推移",
                yaxis_title="利益率 (%)",
                template="plotly_white",
                height=400,
                legend={"orientation": "h", "y": -0.2},
            )
            st.plotly_chart(fig_margin, use_container_width=True)

        # 営業利益推移
        fig_op_income = go.Figure()
        fig_op_income.add_trace(
            go.Bar(
                x=df_history["Year"],
                y=df_history["Operating_Income_M"],
                name="営業利益",
                marker_color=df_history["Operating_Income_M"].apply(color_by_sign),
            )
        )
        fig_op_income.update_layout(
            title=f"{target_company_name} 営業利益推移",
            yaxis_title="営業利益 (百万円)",
            template="plotly_white",
            height=400,
        )
        st.plotly_chart(fig_op_income, use_container_width=True)

        # データテーブル
        st.subheader("📊 財務データ詳細")
        st.dataframe(
            df_history.style.format(
                {
                    "Revenue_M": "¥{:,.0f}",
                    "Operating_Income_M": "¥{:,.0f}",
                    "Operating_Margin": "{:.2%}",
                    "Gross_Margin": "{:.2%}",
                }
            ),
            use_container_width=True,
        )

        # サマリーメトリクス
        latest_year = df_history["Year"].max()
        df_latest = df_history[df_history["Year"] == latest_year].iloc[0]

        st.subheader(f"📊 {latest_year}年度 サマリー")
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "売上高",
            f"¥{df_latest['Revenue_M']:,.0f}M",
            f"{((df_latest['Revenue_M'] / df_history.iloc[0]['Revenue_M'] - 1) * 100):.1f}% (初年度比)",
        )
        col2.metric(
            "営業利益",
            f"¥{df_latest['Operating_Income_M']:,.0f}M",
            f"{df_latest['Operating_Margin']:.1%}",
        )
        col3.metric("売上総利益率", f"{df_latest['Gross_Margin']:.1%}", "")

        st.info(
            f"💡 **分析上のポイント:**\n「{target_company_name}の財務トレンドから、収益性と成長性を確認してください。売上高と利益率の推移を組み合わせることで、収益構造の変化を定量的に把握できます。営業利益率が低下傾向にある場合は、原価構造や費用コントロールの詳細分析が必要です。」"
        )
    else:
        # #7: モックデータ表示（フォールバック）— 理由と対処法を明示
        st.error(
            f"❌ **{target_company_name} ({target_ticker}) の実データを取得できませんでした。**\n\n"
            "**考えられる原因:**\n"
            "- Yahoo Finance に当該企業の財務データが存在しない（非上場・新規上場など）\n"
            "- ティッカーシンボルが誤っている\n\n"
            "**対処法:** サイドバーで正しいティッカー（例: `7433.T`）を直接入力してください。\n\n"
            "以下は **デモデータ** による表示です。実際の財務数値ではありません。"
        )

        mock_history_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            "mock_parts_data_history.csv",
        )
        ensure_historical_marginal_profit_data(mock_history_path)

        if os.path.exists(mock_history_path):
            df_history_pl = load_marginal_profit_data(mock_history_path)
            df_history = df_history_pl.to_pandas()

            fig_ppm_anim = px.scatter(
                df_history,
                x="Total_Revenue",
                y="Avg_Margin",
                animation_frame="Year",
                animation_group="Category",
                size="Total_Volume",
                color="Category",
                hover_name="Category",
                text="Category",
                title="【デモ】PPMマトリクス推移: 縦軸：平均限界利益率 / 横軸：売上高",
                labels={
                    "Total_Revenue": "総売上高 (百万円)",
                    "Avg_Margin": "平均限界利益率",
                },
                template="plotly_white",
                range_x=[max(df_history["Total_Revenue"]) * 1.2, 0],
                range_y=[0, 0.55],
                size_max=80,
                color_discrete_sequence=px.colors.qualitative.Bold,
            )

            fig_ppm_anim.update_traces(textposition="top center")
            if len(fig_ppm_anim.layout.updatemenus) > 0:
                fig_ppm_anim.layout.updatemenus[0].buttons[0].args[1]["frame"][
                    "duration"
                ] = ANIMATION_DURATION_MS
                fig_ppm_anim.layout.updatemenus[0].buttons[0].args[1]["transition"][
                    "duration"
                ] = ANIMATION_TRANSITION_MS

            fig_ppm_anim.update_layout(
                xaxis={"tickformat": "¥,.0f"},
                yaxis={"tickformat": ".1%"},
                height=700,
            )
            st.plotly_chart(fig_ppm_anim, use_container_width=True)
            st.info(
                "ℹ️ これはデモデータです。実際の企業データを表示するには、データ取得が可能な企業ティッカーを選択してください。"
            )
        else:
            st.error("データが取得できませんでした。")
