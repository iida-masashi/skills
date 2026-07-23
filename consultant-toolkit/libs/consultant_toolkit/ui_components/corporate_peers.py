import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from consultant_toolkit.constants import (
    ANIMATION_DURATION_MS,
    ANIMATION_TRANSITION_MS,
    WACC_BENCHMARK,
)


def render_corporate_peers(
    target_ticker,
    target_company_name,
    DYNAMIC_COMPANIES,
    DYNAMIC_COLORS,
    load_financial_data,
    calculate_financial_metrics,
    get_val_safe,
    calculate_comprehensive_metrics,
):
    """
    Main Tab 1: 📂 全社・競合比較 (Corporate & Peers) のレンダリング
    """
    sub_tab1_1, sub_tab1_2, sub_tab1_3 = st.tabs(
        ["📊 競合ベンチマーク", "🏢 全社ROIC動向", "🍕 事業セグメント"]
    )

    # --- 1.1 競合比較ベンチマーク ---
    with sub_tab1_1:
        st.header("1.1 競合比較ベンチマーク (Peer Benchmarking)")
        st.markdown(
            "「主要な競合他社と、主要KGI/KPIを多角的に比較し、自社の立ち位置を明確にします。」"
        )

        @st.cache_data(ttl=3600)
        def get_peer_benchmarking_data(companies_dict):
            # #2: 企業ごとに並列処理してN+1を解消
            def _calc_one(name_ticker):
                name, ticker = name_ticker
                try:
                    income_statement, balance_sheet = load_financial_data(ticker)
                    if income_statement.empty or balance_sheet.empty:
                        return None
                    latest_y = income_statement.columns[0]
                    metrics = calculate_financial_metrics(
                        income_statement, balance_sheet, latest_y
                    )
                    total_assets = get_val_safe(
                        balance_sheet, ["Total Assets"], latest_y
                    )
                    net_income = get_val_safe(
                        income_statement, ["Net Income"], latest_y
                    )
                    equity = get_val_safe(
                        balance_sheet,
                        ["Stockholders Equity", "Total Equity Gross Minority Interest"],
                        latest_y,
                    )
                    revenue = metrics.get("revenue", 0)
                    op_income = metrics.get("operating_income", 0)
                    revenue_growth = 0.0
                    if len(income_statement.columns) >= 2:
                        prev_y = income_statement.columns[1]
                        prev_rev = get_val_safe(
                            income_statement,
                            ["Total Revenue", "Operating Revenue"],
                            prev_y,
                        )
                        if prev_rev > 0:
                            revenue_growth = (revenue / prev_rev) - 1.0
                    return {
                        "Company": name,
                        "Operating Margin (%)": (op_income / revenue * 100)
                        if revenue > 0
                        else 0,
                        "ROIC (%)": metrics.get("roic", 0) * 100,
                        "ROE (%)": (net_income / equity * 100) if equity > 0 else 0,
                        "CCC (Days)": metrics.get("ccc", 0),
                        "Asset Turnover (x)": (revenue / total_assets)
                        if total_assets > 0
                        else 0,
                        "Revenue Growth (%)": revenue_growth * 100,
                    }
                except (ConnectionError, KeyError, ValueError, ZeroDivisionError):
                    return None

            bench_data = []
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [
                    executor.submit(_calc_one, item) for item in companies_dict.items()
                ]
                for future in as_completed(futures):
                    result = future.result()
                    if result is not None:
                        bench_data.append(result)
            # 元の企業順に並べ直す
            order = {name: i for i, name in enumerate(companies_dict.keys())}
            bench_data.sort(key=lambda x: order.get(x["Company"], 999))
            return pd.DataFrame(bench_data)

        df_bench = get_peer_benchmarking_data(DYNAMIC_COMPANIES)
        if not df_bench.empty:
            st.subheader("📊 主要KPI 比較一覧")
            st.dataframe(
                df_bench.set_index("Company").style.format("{:.2f}"),
                use_container_width=True,
            )

            st.subheader("🕸️ 財務・SCM力 比較 (Radar Chart)")
            categories = [
                "Operating Margin (%)",
                "ROIC (%)",
                "ROE (%)",
                "CCC (Days)",
                "Asset Turnover (x)",
                "Revenue Growth (%)",
            ]
            fig_radar = go.Figure()
            for _i, row in df_bench.iterrows():
                r_values = []
                for cat in categories:
                    val = row[cat]
                    if cat == "CCC (Days)":
                        score = max(0, min(100, 100 - (val / 200 * 100)))
                    elif cat == "Asset Turnover (x)":
                        score = max(0, min(100, val * 50))
                    else:
                        score = max(0, min(100, val * 3.33))
                    r_values.append(score)
                r_values.append(r_values[0])
                fig_radar.add_trace(
                    go.Scatterpolar(
                        r=r_values,
                        theta=categories + [categories[0]],
                        fill="toself",
                        name=row["Company"],
                        line={"color": DYNAMIC_COLORS.get(row["Company"])},
                    )
                )
            fig_radar.update_layout(
                polar={"radialaxis": {"visible": True, "range": [0, 100]}},
                template="plotly_white",
                height=600,
            )
            st.plotly_chart(fig_radar, use_container_width=True)
            st.info(
                "💡 **CCCは短いほど効率が良い**ため、外側に表示されるように反転スコア化しているわ。"
            )

    # --- 1.2 全社 ROIC・競合PPM比較 ---
    with sub_tab1_2:
        st.header("1.2 全社 ROIC・競合PPM比較 (10-Year Corporate Portfolio)")
        st.markdown(
            "「縦軸に**ROIC（投下資本利益率）**、横軸に**売上規模**、バブルの大きさを**NOPAT（税引後営業利益）**とした競合PPMマトリクス（過去10年推移）です。自社の資本効率と規模の変遷を競合と相対比較することで、戦略的ポジションを客観的に評価します。」"
        )
        st.markdown(
            "*※注意: Yahoo Finance APIから取得可能な過去データ年数（通常4〜5年）に依存するため、10年分フルで表示されない場合があります。*"
        )

        @st.cache_data(ttl=3600)
        def get_competitor_roic_data(companies_dict):
            # #2: 企業ごとに並列処理してN+1を解消
            def _calc_roic_series(name_ticker):
                name, ticker = name_ticker
                rows = []
                try:
                    income_statement_df, balance_sheet_df = load_financial_data(ticker)
                    if income_statement_df.empty or balance_sheet_df.empty:
                        return rows
                    years = income_statement_df.columns.intersection(
                        balance_sheet_df.columns
                    ).sort_values()
                    for y in years:
                        try:
                            metrics = calculate_financial_metrics(
                                income_statement_df, balance_sheet_df, y
                            )
                            if (
                                metrics["revenue"] > 0
                                and metrics["invested_capital"] > 0
                            ):
                                rows.append(
                                    {
                                        "Company": name,
                                        "Year": str(y.date())[:4],
                                        "Revenue_M": metrics["revenue"] / 1e6,
                                        "NOPAT_M": max(0, metrics["nopat"] / 1e6),
                                        "InvestedCapital_M": metrics["invested_capital"]
                                        / 1e6,
                                        "ROIC": metrics["roic"],
                                    }
                                )
                        except (KeyError, ValueError, ZeroDivisionError):
                            pass
                except (ConnectionError, KeyError, ValueError):
                    pass
                return rows

            all_data = []
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [
                    executor.submit(_calc_roic_series, item)
                    for item in companies_dict.items()
                ]
                for future in as_completed(futures):
                    all_data.extend(future.result())
            return pd.DataFrame(all_data)

        df_comp = get_competitor_roic_data(DYNAMIC_COMPANIES)

        # Save to session state for export
        if "export_data" not in st.session_state:
            st.session_state.export_data = {}
        st.session_state.export_data["roic_comparison"] = df_comp

        if not df_comp.empty:
            df_comp = df_comp.sort_values("Year")

            fig_comp_ppm = px.scatter(
                df_comp,
                x="Revenue_M",
                y="ROIC",
                animation_frame="Year",
                animation_group="Company",
                size="NOPAT_M",
                color="Company",
                hover_name="Company",
                text="Company",
                title="競合他社比較 PPM推移 (過去10年): 縦軸：ROIC / 横軸：売上高 (百万円) / バブル：NOPAT",
                labels={
                    "Revenue_M": "総売上高 (百万円)",
                    "ROIC": "ROIC (投下資本利益率)",
                },
                template="plotly_white",
                range_x=[max(df_comp["Revenue_M"]) * 1.2, 0],
                range_y=[-0.05, max(df_comp["ROIC"]) * 1.5],
                color_discrete_map=DYNAMIC_COLORS,
                size_max=90,
            )

            fig_comp_ppm.add_hline(
                y=WACC_BENCHMARK,
                line_width=2,
                line_dash="dash",
                line_color="red",
                annotation_text="推定WACC (資本コスト: 5%)",
            )
            fig_comp_ppm.update_traces(textposition="top center")

            if len(fig_comp_ppm.layout.updatemenus) > 0:
                fig_comp_ppm.layout.updatemenus[0].buttons[0].args[1]["frame"][
                    "duration"
                ] = ANIMATION_DURATION_MS
                fig_comp_ppm.layout.updatemenus[0].buttons[0].args[1]["transition"][
                    "duration"
                ] = ANIMATION_TRANSITION_MS

            fig_comp_ppm.update_layout(
                xaxis={"tickformat": "¥,.0f"}, yaxis={"tickformat": ".1%"}, height=700
            )
            st.plotly_chart(fig_comp_ppm, use_container_width=True)

            st.dataframe(
                df_comp.style.format(
                    {
                        "ROIC": "{:.2%}",
                        "Revenue_M": "¥{:,.0f}",
                        "NOPAT_M": "¥{:,.0f}",
                        "InvestedCapital_M": "¥{:,.0f}",
                    }
                )
            )
            st.info(
                "💡 **分析上のポイント:**\n「赤い点線はWACC（加重平均資本コスト）の基準値です。ROICがWACCを下回っている企業は「事業活動が企業価値を毀損している（Value Destroyer）」状態にあります。競合他社との相対比較において、右上のStar領域（高ROIC・高規模）にポジションを移行するための資本政策・利益率改善の施策立案が重要です。」"
            )
        else:
            st.warning("競合データの取得・計算に失敗しました。")

    # --- 1.3 事業セグメント分析 ---
    with sub_tab1_3:
        st.header("1.3 事業セグメント別 収益分析 (Business Segment Revenue Analysis)")
        st.markdown(
            "「企業の事業セグメント（製品カテゴリ、地域別）の収益構成を分析します。複数のデータソース（手動マッピング、AI抽出）に対応しています。」"
        )

        # Import segment analysis module
        from consultant_toolkit.segment_analysis import (
            add_segment_mapping,
            get_available_tickers,
            get_segment_analysis,
        )

        # 分析モード選択
        st.subheader("📊 分析設定")
        col_seg1, col_seg2 = st.columns([2, 1])

        with col_seg1:
            use_ai_extraction = st.checkbox(
                "AI自動抽出を使用 (Gemini API)",
                value=False,
                help="手動マッピングにない企業でも、Gemini AIが自動で最新のセグメント情報を抽出します",
            )

        with col_seg2:
            available_tickers = get_available_tickers()
            if target_ticker in available_tickers:
                st.success(f"✅ {target_ticker} はマッピング済み")
            else:
                st.warning(f"⚠️ {target_ticker} は未登録")

        # セグメントデータ取得
        try:
            with st.spinner(f"{target_company_name} のセグメントデータを取得中..."):
                segment_df, geo_df, data_source = get_segment_analysis(
                    target_ticker, use_ai=use_ai_extraction
                )

            st.caption(f"📌 データソース: {data_source}")

            # === 事業セグメント分析 ===
            if segment_df is not None and not segment_df.empty:
                st.subheader("📈 事業セグメント別 収益構成")

                col_biz1, col_biz2 = st.columns([3, 2])

                with col_biz1:
                    # パイチャート
                    fig_seg_pie = go.Figure(
                        data=[
                            go.Pie(
                                labels=segment_df["Segment"],
                                values=segment_df["Revenue"],
                                hole=0.4,
                                textinfo="label+percent",
                                hovertemplate="<b>%{label}</b><br>収益: %{value:,.0f}M<br>割合: %{percent}<extra></extra>",
                            )
                        ]
                    )

                    fig_seg_pie.update_layout(
                        title=f"{target_company_name} 事業セグメント構成",
                        template="plotly_white",
                        showlegend=True,
                        height=400,
                    )

                    st.plotly_chart(fig_seg_pie, use_container_width=True)

                with col_biz2:
                    # データテーブル
                    st.markdown("##### セグメント詳細")
                    display_df = segment_df.copy()
                    display_df["Revenue"] = display_df["Revenue"].apply(
                        lambda x: f"{x:,.0f}M"
                    )
                    display_df["Percentage"] = display_df["Percentage"].apply(
                        lambda x: f"{x:.1f}%"
                    )
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

                # 棒グラフ
                st.divider()
                fig_seg_bar = go.Figure(
                    data=[
                        go.Bar(
                            x=segment_df["Segment"],
                            y=segment_df["Revenue"],
                            marker_color="#1f77b4",
                            text=segment_df["Percentage"].apply(lambda x: f"{x:.1f}%"),
                            textposition="outside",
                            hovertemplate="<b>%{x}</b><br>収益: %{y:,.0f}M<br>%{text}<extra></extra>",
                        )
                    ]
                )

                fig_seg_bar.update_layout(
                    title="セグメント別 収益額 (単位: 百万)",
                    xaxis_title="事業セグメント",
                    yaxis_title="収益 (Million)",
                    template="plotly_white",
                    height=400,
                )

                st.plotly_chart(fig_seg_bar, use_container_width=True)

                # Insight
                top_segment = segment_df.iloc[0]
                top_segment_name = top_segment["Segment"]
                top_segment_pct = top_segment["Percentage"]

                if top_segment_pct > 50:
                    risk_level = "🔴 高リスク"
                    risk_msg = f"収益の{top_segment_pct:.1f}%を「{top_segment_name}」に依存しているわ。**集中リスクが高すぎる**わね。他セグメントの育成が急務よ。"
                elif top_segment_pct > 30:
                    risk_level = "🟡 中リスク"
                    risk_msg = f"「{top_segment_name}」が{top_segment_pct:.1f}%を占めているわ。主力事業としては健全だけど、**多角化余地**はあるわね。"
                else:
                    risk_level = "🟢 分散良好"
                    risk_msg = "事業ポートフォリオは比較的バランスが取れているわ。リスク分散できてるわね。"

                st.info(f"💡 **Consultant's Insight:** {risk_level}\n{risk_msg}")

            else:
                st.warning(
                    f"⚠️ {target_company_name} ({target_ticker}) の事業セグメントデータが取得できませんでした。"
                )
                st.markdown("""
    **対処法:**
    1. ✅ 「AI自動抽出を使用」をONにして再実行（Gemini APIキーが必要）
    2. ✅ 手動でセグメントマッピングを追加（下記フォームから登録可能）
                """)

            # === 地域セグメント分析 ===
            st.divider()
            st.subheader("🌍 地域別 収益構成 (Geographic Revenue)")

            if geo_df is not None and not geo_df.empty:
                col_geo1, col_geo2 = st.columns([3, 2])

                with col_geo1:
                    # 地域別パイチャート
                    fig_geo_pie = go.Figure(
                        data=[
                            go.Pie(
                                labels=geo_df["Region"],
                                values=geo_df["Revenue"],
                                hole=0.4,
                                textinfo="label+percent",
                                hovertemplate="<b>%{label}</b><br>収益: %{value:,.0f}M<br>割合: %{percent}<extra></extra>",
                            )
                        ]
                    )

                    fig_geo_pie.update_layout(
                        title=f"{target_company_name} 地域別収益構成",
                        template="plotly_white",
                        height=400,
                    )

                    st.plotly_chart(fig_geo_pie, use_container_width=True)

                with col_geo2:
                    # データテーブル
                    st.markdown("##### 地域詳細")
                    display_geo = geo_df.copy()
                    display_geo["Revenue"] = display_geo["Revenue"].apply(
                        lambda x: f"{x:,.0f}M"
                    )
                    display_geo["Percentage"] = display_geo["Percentage"].apply(
                        lambda x: f"{x:.1f}%"
                    )
                    st.dataframe(display_geo, use_container_width=True, hide_index=True)

            else:
                st.info("ℹ️ 地域別セグメントデータは現在利用できません。")

            # === カスタムセグメント登録フォーム ===
            st.divider()
            st.subheader("🔧 カスタムセグメント登録 (Advanced)")

            with st.expander("新しい企業のセグメントマッピングを追加"):
                st.markdown("手動でセグメント情報を登録できます（JSON形式）")

                custom_ticker = st.text_input("ティッカーシンボル", value=target_ticker)
                custom_company = st.text_input("企業名", value=target_company_name)

                st.markdown("**セグメント定義（JSON形式）**")
                sample_json = {
                    "Product A": {"percentage": 0.50, "description": "主力製品"},
                    "Product B": {"percentage": 0.30, "description": "成長製品"},
                    "Product C": {"percentage": 0.20, "description": "新規事業"},
                }

                segment_json = st.text_area(
                    "セグメントJSON",
                    value=json.dumps(sample_json, indent=2, ensure_ascii=False),
                    height=200,
                    key="corporate_peers_segment_json",
                )

                custom_fy = st.number_input(
                    "会計年度", min_value=2020, max_value=2030, value=2023
                )

                if st.button("登録"):
                    try:
                        segments_dict = json.loads(segment_json)
                        # #8: 構造バリデーション
                        if (
                            not isinstance(segments_dict, dict)
                            or len(segments_dict) == 0
                        ):
                            st.error(
                                "セグメントは1件以上のキーを持つオブジェクトで入力してください。"
                            )
                        else:
                            total_pct = sum(
                                v.get("percentage", 0) if isinstance(v, dict) else 0
                                for v in segments_dict.values()
                            )
                            if abs(total_pct - 1.0) > 0.02:
                                st.warning(
                                    f"⚠️ percentage の合計が {total_pct:.2f} です（合計1.0 = 100% を推奨）。"
                                    "このまま登録しますか？登録する場合は再度「登録」を押してください。",
                                )
                                st.session_state["seg_validation_pending"] = True
                            else:
                                st.session_state["seg_validation_pending"] = False

                            if not st.session_state.get(
                                "seg_validation_pending", False
                            ):
                                add_segment_mapping(
                                    ticker=custom_ticker,
                                    company_name=custom_company,
                                    segments=segments_dict,
                                    fiscal_year=custom_fy,
                                    source="User Custom",
                                )
                                st.success(
                                    f"✅ {custom_ticker} のセグメントマッピングを登録しました！"
                                )
                                st.session_state["seg_validation_pending"] = False
                    except json.JSONDecodeError as e:
                        st.error(f"JSON形式が不正です: {e}")
                    except (KeyError, ValueError, OSError) as e:
                        st.error(f"登録失敗: {e}")

        except (ConnectionError, KeyError, ValueError, TypeError) as e:
            st.error(f"セグメント分析でエラーが発生しました: {e}")
            st.exception(e)
