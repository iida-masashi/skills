import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_ccc_analysis(
    target_company_name,
    DYNAMIC_COMPANIES,
    load_financial_data,
    calculate_ccc_metrics,
    load_markdown_asset,
):
    """
    サブタブ 2.3: 🔄 CCC・運転資本詳細分析 のレンダリング
    """
    st.header("2.3 CCC (キャッシュ・コンバージョン・サイクル) 詳細分析")
    st.markdown(
        "サプライチェーンの効率性を示す**運転資本（CCC）**を分解・分析します。在庫の滞留・回収サイトの長期化・支払条件の変化が、いかに企業の資金繰りと成長投資余力に影響するかを定量的に把握します。"
    )

    with st.expander("📖 CCC・各指標の計算式と解説", expanded=False):
        st.markdown(load_markdown_asset("ccc_explanation.md"))

    @st.cache_data(ttl=3600)
    def get_ccc_data(companies_dict):
        ccc_data = []
        hist_ccc_data = []
        target_company_name_local = list(companies_dict.keys())[0]

        for name, ticker in companies_dict.items():
            income_statement_df, balance_sheet_df = load_financial_data(ticker)
            if income_statement_df.empty or balance_sheet_df.empty:
                continue

            # 直近年のCCC構造
            y = income_statement_df.columns[0]
            metrics = calculate_ccc_metrics(
                income_statement_df, balance_sheet_df, y
            )

            if metrics["revenue"] > 0:
                ccc_data.append(
                    {
                        "Company": name,
                        "CCC (Days)": metrics["ccc"],
                        "DIO (Days)": metrics["dio"],
                        "DSO (Days)": metrics["dso"],
                        "DPO (Days)": metrics["dpo"],
                    }
                )

            # 対象企業の過去推移を取得 (詳細データ付き)
            if name == target_company_name_local:
                years = income_statement_df.columns.intersection(
                    balance_sheet_df.columns
                ).sort_values()
                for hist_y in years:
                    hist_metrics = calculate_ccc_metrics(
                        income_statement_df, balance_sheet_df, hist_y
                    )

                    if hist_metrics["revenue"] > 0:
                        hist_ccc_data.append(
                            {
                                "Year": str(hist_y.date())[:4],
                                "CCC": hist_metrics["ccc"],
                                "DIO (在庫)": hist_metrics["dio"],
                                "DSO (売掛)": hist_metrics["dso"],
                                "DPO (買掛)": hist_metrics["dpo"],
                                # 金額データ (百万円)
                                "Revenue": hist_metrics["revenue"] / 1e6,
                                "COGS": hist_metrics["cogs"] / 1e6,
                                "Inventory": hist_metrics["inventory"] / 1e6,
                                "Receivables": hist_metrics["receivables"] / 1e6,
                                "Payables": hist_metrics["payables"] / 1e6,
                            }
                        )

        return pd.DataFrame(ccc_data) if ccc_data else pd.DataFrame(), pd.DataFrame(
            hist_ccc_data
        ).sort_values("Year") if hist_ccc_data else pd.DataFrame()

    # #4: データ取得とUI描画を別ブロックに分離
    try:
        df_ccc, df_hist_ccc = get_ccc_data(DYNAMIC_COMPANIES)
    except (ConnectionError, KeyError, ValueError) as e:
        st.error(f"CCCデータの取得に失敗しました: {e}")
        df_ccc, df_hist_ccc = pd.DataFrame(), pd.DataFrame()

    try:
        if not df_ccc.empty:
            # サブタブで詳細分析
            subtab_names = [
                "📊 Overview",
                "📦 在庫(DIO)詳細",
                "🤝 売掛(DSO)詳細",
                "💸 買掛(DPO)詳細",
                "💰 キャッシュ改善Sim",
            ]
            st_ccc_tabs = st.tabs(subtab_names)

            # 1. Overview
            with st_ccc_tabs[0]:
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    fig_ccc = go.Figure()
                    fig_ccc.add_trace(
                        go.Bar(
                            name="DIO (在庫日数: 悪化要因)",
                            x=df_ccc["Company"],
                            y=df_ccc["DIO (Days)"],
                            marker_color="#ff7f0e",
                        )
                    )
                    fig_ccc.add_trace(
                        go.Bar(
                            name="DSO (売上債権: 悪化要因)",
                            x=df_ccc["Company"],
                            y=df_ccc["DSO (Days)"],
                            marker_color="#1f77b4",
                        )
                    )
                    fig_ccc.add_trace(
                        go.Bar(
                            name="DPO (仕入債務: 改善要因)",
                            x=df_ccc["Company"],
                            y=-df_ccc["DPO (Days)"],
                            marker_color="#2ca02c",
                        )
                    )

                    fig_ccc.update_layout(
                        title="競合 CCC構造比較 (直近年度)",
                        barmode="relative",
                        yaxis_title="Days",
                        template="plotly_white",
                        legend={
                            "orientation": "h",
                            "yanchor": "bottom",
                            "y": 1.02,
                            "xanchor": "right",
                            "x": 1,
                        },
                    )
                    fig_ccc.add_trace(
                        go.Scatter(
                            name="CCC (純運転資本回転日数)",
                            x=df_ccc["Company"],
                            y=df_ccc["CCC (Days)"],
                            mode="lines+markers",
                            marker={"color": "#d62728", "size": 12},
                        )
                    )
                    st.plotly_chart(fig_ccc, use_container_width=True)

                with col_c2:
                    if not df_hist_ccc.empty:
                        fig_hist = go.Figure()
                        fig_hist.add_trace(
                            go.Bar(
                                name="DIO (在庫)",
                                x=df_hist_ccc["Year"],
                                y=df_hist_ccc["DIO (在庫)"],
                                marker_color="#ff7f0e",
                            )
                        )
                        fig_hist.add_trace(
                            go.Bar(
                                name="DSO (売掛)",
                                x=df_hist_ccc["Year"],
                                y=df_hist_ccc["DSO (売掛)"],
                                marker_color="#1f77b4",
                            )
                        )
                        fig_hist.add_trace(
                            go.Bar(
                                name="DPO (買掛)",
                                x=df_hist_ccc["Year"],
                                y=-df_hist_ccc["DPO (買掛)"],
                                marker_color="#2ca02c",
                            )
                        )
                        fig_hist.add_trace(
                            go.Scatter(
                                name="CCC (合計)",
                                x=df_hist_ccc["Year"],
                                y=df_hist_ccc["CCC"],
                                mode="lines+markers",
                                marker={"color": "#d62728", "size": 10},
                                line={"width": 3},
                            )
                        )
                        fig_hist.update_layout(
                            title=f"{target_company_name} CCC 過去推移 (滞留要因の特定)",
                            barmode="relative",
                            yaxis_title="Days",
                            template="plotly_white",
                            legend={
                                "orientation": "h",
                                "yanchor": "bottom",
                                "y": 1.02,
                                "xanchor": "right",
                                "x": 1,
                            },
                        )
                        st.plotly_chart(fig_hist, use_container_width=True)

            # 2. DIO詳細
            with st_ccc_tabs[1]:
                if not df_hist_ccc.empty:
                    st.subheader("在庫回転日数 (DIO) と 在庫金額の推移")

                    col_dio_info, col_dio_chart = st.columns([1, 2])
                    with col_dio_info:
                        st.markdown("""
    **📦 DIO (Days Inventory Outstanding)**

    #### 計算式
    ```
    DIO = 棚卸資産 ÷ 売上原価 × 365
    ```

    #### 意味
    仕入れた原材料・仕掛品・製品が、
    何日間在庫として滞留するかを示す。

    #### 判断基準
    | DIO | 評価 |
    |-----|------|
    | 低下トレンド | ✅ 在庫効率改善 |
    | 横ばい | ➖ 現状維持 |
    | 上昇トレンド | ⚠️ 滞留在庫の疑い |

    #### 改善のポイント
    - 需要予測精度の向上（S&OP）
    - 安全在庫水準の最適化
    - サプライヤーとの小ロット・高頻度納入
    - 死に在庫（slow-moving）の定期評価
                            """)
                    with col_dio_chart:
                        fig_dio = go.Figure()
                        fig_dio.add_trace(
                            go.Bar(
                                name="在庫金額 (百万円)",
                                x=df_hist_ccc["Year"],
                                y=df_hist_ccc["Inventory"],
                                marker_color="#ff7f0e",
                                opacity=0.6,
                            )
                        )
                        fig_dio.add_trace(
                            go.Scatter(
                                name="DIO (日)",
                                x=df_hist_ccc["Year"],
                                y=df_hist_ccc["DIO (在庫)"],
                                yaxis="y2",
                                mode="lines+markers",
                                line={"color": "#d62728", "width": 3},
                            )
                        )
                        fig_dio.update_layout(
                            title="在庫の膨張と回転の鈍化",
                            yaxis={
                                "title": "在庫金額 (百万円)",
                                "side": "left",
                                "showgrid": False,
                            },
                            yaxis2={
                                "title": "DIO (日)",
                                "side": "right",
                                "overlaying": "y",
                                "showgrid": True,
                            },
                            template="plotly_white",
                            legend={"orientation": "h", "y": 1.1},
                        )
                        st.plotly_chart(fig_dio, use_container_width=True)
                    st.info(
                        "💡 **分析上のポイント:**\n在庫金額が増加していても、DIO（在庫回転日数）が横ばいであれば「売上増に伴う適正在庫の拡大」と評価できます。一方、DIOが悪化（長期化）しながら在庫金額も増加している場合は、**需要予測の精度低下や過剰発注による滞留在庫の蓄積**を示唆しており、キャッシュの固定化・廃棄損リスクの観点から早期の対策が求められます。"
                    )

            # 3. DSO詳細
            with st_ccc_tabs[2]:
                if not df_hist_ccc.empty:
                    st.subheader("売上債権回転日数 (DSO) と 売掛金残高の推移")

                    col_dso_info, col_dso_chart = st.columns([1, 2])
                    with col_dso_info:
                        st.markdown("""
    **🤝 DSO (Days Sales Outstanding)**

    #### 計算式
    ```
    DSO = 売上債権 ÷ 売上高 × 365
    ```
    ※ 売上債権 = 売掛金 + 受取手形

    #### 意味
    製品・サービスを販売してから、
    実際に代金を回収するまでの日数。

    #### 判断基準
    | DSO | 評価 |
    |-----|------|
    | 低下トレンド | ✅ 回収効率改善 |
    | 横ばい | ➖ 現状維持 |
    | 上昇トレンド | ⚠️ 回収遅延・貸倒れリスク |

    #### 改善のポイント
    - 早期支払い割引制度の導入
    - 請求〜入金プロセスの自動化
    - 顧客ごとの与信管理強化
    - 長期滞留債権の早期対応
                            """)
                    with col_dso_chart:
                        fig_dso = go.Figure()
                        fig_dso.add_trace(
                            go.Bar(
                                name="売掛金 (百万円)",
                                x=df_hist_ccc["Year"],
                                y=df_hist_ccc["Receivables"],
                                marker_color="#1f77b4",
                                opacity=0.6,
                            )
                        )
                        fig_dso.add_trace(
                            go.Scatter(
                                name="DSO (日)",
                                x=df_hist_ccc["Year"],
                                y=df_hist_ccc["DSO (売掛)"],
                                yaxis="y2",
                                mode="lines+markers",
                                line={"color": "#d62728", "width": 3},
                            )
                        )
                        fig_dso.update_layout(
                            title="回収サイトの変動",
                            yaxis={
                                "title": "売掛金 (百万円)", "side": "left", "showgrid": False
                            },
                            yaxis2={
                                "title": "DSO (日)",
                                "side": "right",
                                "overlaying": "y",
                                "showgrid": True,
                            },
                            template="plotly_white",
                            legend={"orientation": "h", "y": 1.1},
                        )
                        st.plotly_chart(fig_dso, use_container_width=True)

            # 4. DPO詳細
            with st_ccc_tabs[3]:
                if not df_hist_ccc.empty:
                    st.subheader("仕入債務回転日数 (DPO) と 買掛金残高の推移")

                    col_dpo_info, col_dpo_chart = st.columns([1, 2])
                    with col_dpo_info:
                        st.markdown("""
    **💸 DPO (Days Payable Outstanding)**

    #### 計算式
    ```
    DPO = 仕入債務 ÷ 売上原価 × 365
    ```
    ※ 仕入債務 = 買掛金 + 支払手形

    #### 意味
    仕入れ代金を何日後に支払うかを示す。
    DIOやDSOと異なり、**長い方がCCC改善**になる。

    #### 判断基準
    | DPO | 評価 |
    |-----|------|
    | 上昇トレンド | ✅ 支払サイト延長・資金効率向上 |
    | 横ばい | ➖ 現状維持 |
    | 低下トレンド | ⚠️ 支払いの前倒し・交渉力低下 |

    #### 改善のポイント
    - サプライヤーとの支払いサイト再交渉
    - 支払い条件の標準化（60日→90日など）
    - ただし**過度な延長はサプライヤーの経営を圧迫し**、
      調達リスクにつながるため要注意
                            """)
                    with col_dpo_chart:
                        fig_dpo = go.Figure()
                        fig_dpo.add_trace(
                            go.Bar(
                                name="買掛金 (百万円)",
                                x=df_hist_ccc["Year"],
                                y=df_hist_ccc["Payables"],
                                marker_color="#2ca02c",
                                opacity=0.6,
                            )
                        )
                        fig_dpo.add_trace(
                            go.Scatter(
                                name="DPO (日)",
                                x=df_hist_ccc["Year"],
                                y=df_hist_ccc["DPO (買掛)"],
                                yaxis="y2",
                                mode="lines+markers",
                                line={"color": "#d62728", "width": 3},
                            )
                        )
                        fig_dpo.update_layout(
                            title="支払サイトの変動",
                            yaxis={
                                "title": "買掛金 (百万円)", "side": "left", "showgrid": False
                            },
                            yaxis2={
                                "title": "DPO (日)",
                                "side": "right",
                                "overlaying": "y",
                                "showgrid": True,
                            },
                            template="plotly_white",
                            legend={"orientation": "h", "y": 1.1},
                        )
                        st.plotly_chart(fig_dpo, use_container_width=True)

            # 5. キャッシュ改善シミュレーション
            with st_ccc_tabs[4]:
                st.subheader("💰 CCC改善によるキャッシュ創出効果シミュレーション")
                if not df_hist_ccc.empty:
                    latest = df_hist_ccc.iloc[-1]
                    st.markdown(
                        f"**基準年度: {latest['Year']}** (売上: ¥{latest['Revenue']:,.0f}M, 原価: ¥{latest['COGS']:,.0f}M)"
                    )

                    col_s1, col_s2, col_s3 = st.columns(3)
                    with col_s1:
                        st.metric(
                            "現在の在庫 (DIO)",
                            f"{latest['DIO (在庫)']:.1f} 日",
                            f"¥ {latest['Inventory']:,.0f} M",
                        )
                        target_dio = st.slider(
                            "目標 DIO (日)",
                            0.0,
                            float(latest["DIO (在庫)"]),
                            float(latest["DIO (在庫)"]),
                            0.5,
                        )
                    with col_s2:
                        st.metric(
                            "現在の売掛 (DSO)",
                            f"{latest['DSO (売掛)']:.1f} 日",
                            f"¥ {latest['Receivables']:,.0f} M",
                        )
                        target_dso = st.slider(
                            "目標 DSO (日)",
                            0.0,
                            float(latest["DSO (売掛)"]),
                            float(latest["DSO (売掛)"]),
                            0.5,
                        )
                    with col_s3:
                        st.metric(
                            "現在の買掛 (DPO)",
                            f"{latest['DPO (買掛)']:.1f} 日",
                            f"¥ {latest['Payables']:,.0f} M",
                        )
                        target_dpo = st.slider(
                            "目標 DPO (日)",
                            float(latest["DPO (買掛)"]),
                            float(latest["DPO (買掛)"] + 60),
                            float(latest["DPO (買掛)"]),
                            0.5,
                        )

                    # 計算
                    # 1日あたりの金額
                    daily_cogs = latest["COGS"] / 365
                    daily_rev = latest["Revenue"] / 365

                    improved_inv = daily_cogs * target_dio
                    improved_ar = daily_rev * target_dso
                    improved_ap = daily_cogs * target_dpo

                    cash_generated_inv = latest["Inventory"] - improved_inv
                    cash_generated_ar = latest["Receivables"] - improved_ar
                    cash_generated_ap = (
                        improved_ap - latest["Payables"]
                    )  # DPO増 = 支払遅延 = キャッシュ増

                    total_cash_generated = (
                        cash_generated_inv + cash_generated_ar + cash_generated_ap
                    )

                    st.divider()
                    st.subheader(
                        f"🎉 改善によるキャッシュ創出額: ¥ {total_cash_generated:,.0f} 百万円"
                    )

                    c_gen1, c_gen2, c_gen3 = st.columns(3)
                    c_gen1.metric(
                        "在庫圧縮効果", f"+ ¥ {cash_generated_inv:,.0f} M"
                    )
                    c_gen2.metric("早期回収効果", f"+ ¥ {cash_generated_ar:,.0f} M")
                    c_gen3.metric("支払延長効果", f"+ ¥ {cash_generated_ap:,.0f} M")

                    st.progress(
                        min(
                            1.0,
                            max(
                                0.0,
                                total_cash_generated / (latest["Revenue"] * 0.2),
                            ),
                        )
                    )  # バーの長さ適当
                    st.markdown("※ 原価ベースで計算（簡易シミュレーション）")

            st.info(
                "💡 **分析上のポイント:**\nキャッシュ改善シミュレーションでは、DIO・DSO・DPOを業界ベストプラクティス水準に引き寄せた場合の資金創出効果を試算できます。在庫回転日数をわずか数日改善するだけで、数億円規模の運転資本が解放されるケースも珍しくありません。これが**「SCM最適化＝財務改善」**の本質です。解放されたキャッシュは、有利子負債の削減や次の成長投資（Tab 6: CAPEX分析）への原資として検討してください。"
            )

    except (KeyError, ValueError, TypeError) as e:
        st.error(f"CCC分析の描画中にエラーが発生しました: {e}")
