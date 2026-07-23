import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render_roic_tree(
    target_ticker,
    DYNAMIC_COMPANIES,
    DYNAMIC_COLORS,
    load_financial_data,
    calculate_financial_metrics,
    get_val_safe,
    load_markdown_asset,
    DAYS_PER_YEAR=365,
    WACC_BENCHMARK=0.05,
):
    """
    サブタブ 2.2: 🌳 高度なROICツリー分析 (DuPont Decomposition) のレンダリング
    """
    st.header("2.2 🌳 高度なROICツリー分析 (DuPont Decomposition)")
    st.markdown(
        "投下資本利益率(ROIC)を**多段階に分解**し、収益性と効率性の真のドライバーを特定します。"
    )

    with st.expander("📖 ROIC・NOPAT・IC Turnoverの計算式と解説", expanded=False):
        st.markdown(load_markdown_asset("roic_explanation.md"))

    @st.cache_data(ttl=3600)
    def get_advanced_roic_tree_data(companies_dict):
        """拡張ROICツリーデータ取得（歴史データ含む）"""
        tree_data = []
        historical_data = []

        for name, ticker in companies_dict.items():
            income_statement_df, balance_sheet_df = load_financial_data(ticker)
            if income_statement_df.empty or balance_sheet_df.empty:
                continue

            # 直近年度（メイン分析用）
            y_latest = income_statement_df.columns[0]
            metrics_latest = calculate_financial_metrics(
                income_statement_df, balance_sheet_df, y_latest
            )

            if (
                metrics_latest["revenue"] > 0
                and metrics_latest["invested_capital"] > 0
            ):
                # 追加メトリクス計算
                total_assets = get_val_safe(
                    balance_sheet_df, ["Total Assets"], y_latest
                )
                equity = get_val_safe(
                    balance_sheet_df,
                    ["Total Equity Gross Minority Interest", "Stockholders Equity"],
                    y_latest,
                )
                debt = get_val_safe(balance_sheet_df, ["Total Debt"], y_latest)

                asset_turnover = (
                    metrics_latest["revenue"] / total_assets
                    if total_assets > 0
                    else 0
                )
                leverage = total_assets / equity if equity > 0 else 0
                debt_ratio = debt / total_assets if total_assets > 0 else 0

                tree_data.append(
                    {
                        "Company": name,
                        "ROIC (%)": metrics_latest["roic"] * 100,
                        "NOPAT Margin (%)": metrics_latest["nopat_margin"] * 100,
                        "IC Turnover (x)": metrics_latest["ic_turnover"],
                        "Asset Turnover (x)": asset_turnover,
                        "Leverage (x)": leverage,
                        "Debt Ratio (%)": debt_ratio * 100,
                        "Revenue (M)": metrics_latest["revenue"] / 1e6,
                        "NOPAT (M)": metrics_latest["nopat"] / 1e6,
                    }
                )

            # 過去推移（トレンド分析用）
            years = income_statement_df.columns.sort_values()
            for y in years:
                try:
                    metrics = calculate_financial_metrics(
                        income_statement_df, balance_sheet_df, y
                    )
                    if metrics["revenue"] > 0:
                        historical_data.append(
                            {
                                "Company": name,
                                "Year": str(y.date())[:4],
                                "ROIC (%)": metrics["roic"] * 100,
                                "NOPAT Margin (%)": metrics["nopat_margin"] * 100,
                                "IC Turnover (x)": metrics["ic_turnover"],
                            }
                        )
                except (KeyError, ValueError, ZeroDivisionError):
                    pass

        return (
            pd.DataFrame(tree_data) if tree_data else pd.DataFrame(),
            pd.DataFrame(historical_data) if historical_data else pd.DataFrame(),
        )

    # #4: データ取得とUI描画を別ブロックに分離
    try:
        df_tree, df_historical = get_advanced_roic_tree_data(DYNAMIC_COMPANIES)
    except (ConnectionError, KeyError, ValueError) as e:
        st.error(f"ROICツリーデータの取得に失敗しました: {e}")
        df_tree, df_historical = pd.DataFrame(), pd.DataFrame()

    try:
        if not df_tree.empty:
            # サブタブで詳細分析
            roic_tabs = st.tabs(
                [
                    "📊 ROICツリー分解",
                    "📈 歴史トレンド",
                    "🔬 詳細メトリクス",
                    "🎯 ベンチマーク分析",
                    "🚀 ROIC改善シミュレーション",
                ]
            )

            # Tab 1: ROICツリー分解（基本）
            with roic_tabs[0]:
                st.subheader("ROIC = NOPAT Margin × IC Turnover")
                st.markdown("""
    **ROIC** は収益性と効率性の2つのドライバーに分解されます。散布図の各象限の位置が、競合との戦略的差異を示します。

    | 指標 | 計算式 | 意味 |
    |------|--------|------|
    | **ROIC (%)** | `NOPAT ÷ 投下資本 × 100` | 総合的な資本効率 |
    | **NOPAT Margin (%)** | `営業利益×(1−税率) ÷ 売上高 × 100` | 収益性ドライバー |
    | **IC Turnover (x)** | `売上高 ÷ 投下資本` | 効率性ドライバー |
                """)

                col1, col2 = st.columns(2)

                with col1:
                    # メインチャート: マージン vs 回転率
                    fig_tree = px.scatter(
                        df_tree,
                        x="NOPAT Margin (%)",
                        y="IC Turnover (x)",
                        color="Company",
                        size="ROIC (%)",
                        text="Company",
                        title="ROICツリー: 収益性 vs 効率性",
                        template="plotly_white",
                        size_max=50,
                        color_discrete_map=DYNAMIC_COLORS,
                        hover_data=["ROIC (%)", "Revenue (M)"],
                    )

                    # ベンチマークライン追加
                    fig_tree.add_vline(
                        x=df_tree["NOPAT Margin (%)"].median(),
                        line_dash="dot",
                        line_color="gray",
                        annotation_text="業界中央値",
                    )
                    fig_tree.add_hline(
                        y=df_tree["IC Turnover (x)"].median(),
                        line_dash="dot",
                        line_color="gray",
                        annotation_text="業界中央値",
                    )

                    fig_tree.update_traces(textposition="top center")
                    fig_tree.update_layout(height=500)
                    st.plotly_chart(fig_tree, use_container_width=True)

                with col2:
                    # ROICバーチャート
                    fig_roic_bar = px.bar(
                        df_tree.sort_values("ROIC (%)", ascending=False),
                        x="Company",
                        y="ROIC (%)",
                        color="ROIC (%)",
                        title="ROIC ランキング",
                        template="plotly_white",
                        color_continuous_scale="RdYlGn",
                    )
                    fig_roic_bar.add_hline(
                        y=WACC_BENCHMARK * 100,
                        line_dash="dash",
                        line_color="red",
                        annotation_text=f"WACC ({WACC_BENCHMARK * 100:.0f}%)",
                    )
                    fig_roic_bar.update_layout(height=500, showlegend=False)
                    st.plotly_chart(fig_roic_bar, use_container_width=True)

                # 戦略ポジショニングマトリクス
                st.markdown("### 📍 戦略ポジショニング")
                st.markdown("""
                    **4象限分析:**
                    - **右上（⭐Star）**: 高マージン × 高回転 → 理想的
                    - **右下（💎Premium）**: 高マージン × 低回転 → 高付加価値戦略
                    - **左上（⚡Fast Mover）**: 低マージン × 高回転 → 薄利多売戦略
                    - **左下（⚠️Dog）**: 低マージン × 低回転 → 改善必須
                    """)

            # Tab 2: 歴史トレンド
            with roic_tabs[1]:
                if not df_historical.empty:
                    st.subheader("ROIC構成要素の推移")
                    st.markdown(f"""
    各指標の過去トレンドを確認することで、ROIC変動の**根本要因がマージン低下（収益性悪化）か、IC Turnover低下（資本効率悪化）かを判別**できます。
    赤い破線はWACCベンチマーク（{WACC_BENCHMARK * 100:.0f}%）を示します。この水準を下回る期間は、資本コストを賄えず企業価値を毀損している状態を意味します。
                        """)

                    # ROIC推移
                    fig_roic_trend = px.line(
                        df_historical,
                        x="Year",
                        y="ROIC (%)",
                        color="Company",
                        markers=True,
                        title="ROIC 推移（過去5-7年）",
                        template="plotly_white",
                        color_discrete_map=DYNAMIC_COLORS,
                    )
                    fig_roic_trend.add_hline(
                        y=WACC_BENCHMARK * 100, line_dash="dash", line_color="red"
                    )
                    fig_roic_trend.update_layout(height=400)
                    st.plotly_chart(fig_roic_trend, use_container_width=True)

                    col1, col2 = st.columns(2)

                    with col1:
                        # NOPATマージン推移
                        fig_margin_trend = px.line(
                            df_historical,
                            x="Year",
                            y="NOPAT Margin (%)",
                            color="Company",
                            markers=True,
                            title="NOPAT Margin 推移",
                            template="plotly_white",
                            color_discrete_map=DYNAMIC_COLORS,
                        )
                        fig_margin_trend.update_layout(height=350)
                        st.plotly_chart(fig_margin_trend, use_container_width=True)

                    with col2:
                        # IC回転率推移
                        fig_turnover_trend = px.line(
                            df_historical,
                            x="Year",
                            y="IC Turnover (x)",
                            color="Company",
                            markers=True,
                            title="IC Turnover 推移",
                            template="plotly_white",
                            color_discrete_map=DYNAMIC_COLORS,
                        )
                        fig_turnover_trend.update_layout(height=350)
                        st.plotly_chart(
                            fig_turnover_trend, use_container_width=True
                        )
                else:
                    st.warning("歴史データがありません")

            # Tab 3: 詳細メトリクス
            with roic_tabs[2]:
                st.subheader("財務レバレッジとアセット効率")
                st.markdown("""
    **総資産回転率（Asset Turnover）** は、総資産全体に対する売上の効率を示します。IC Turnoverとの違いは、**有利子負債・株主資本のみ**を分母とするか、**総資産全体**を分母とするかにあります。
    **財務レバレッジ（Leverage）** は総資産÷株主資本であり、値が高いほど負債依存度が高いことを意味します。レバレッジはROEを押し上げますが、財務リスクも同時に増大させます。
                    """)

                col1, col2 = st.columns(2)

                with col1:
                    # Asset Turnover
                    fig_asset = px.bar(
                        df_tree.sort_values("Asset Turnover (x)", ascending=False),
                        x="Company",
                        y="Asset Turnover (x)",
                        title="総資産回転率 (Asset Turnover)",
                        template="plotly_white",
                        color="Asset Turnover (x)",
                        color_continuous_scale="Blues",
                    )
                    fig_asset.update_layout(height=400, showlegend=False)
                    st.plotly_chart(fig_asset, use_container_width=True)

                with col2:
                    # Leverage
                    fig_leverage = px.bar(
                        df_tree.sort_values("Leverage (x)", ascending=False),
                        x="Company",
                        y="Leverage (x)",
                        title="財務レバレッジ (Assets/Equity)",
                        template="plotly_white",
                        color="Leverage (x)",
                        color_continuous_scale="Oranges",
                    )
                    fig_leverage.update_layout(height=400, showlegend=False)
                    st.plotly_chart(fig_leverage, use_container_width=True)

                # 詳細データテーブル
                st.subheader("📋 詳細メトリクス一覧")
                st.dataframe(
                    df_tree.style.format(
                        {
                            "ROIC (%)": "{:.2f}%",
                            "NOPAT Margin (%)": "{:.2f}%",
                            "IC Turnover (x)": "{:.2f}",
                            "Asset Turnover (x)": "{:.2f}",
                            "Leverage (x)": "{:.2f}",
                            "Debt Ratio (%)": "{:.2f}%",
                            "Revenue (M)": "¥{:,.0f}M",
                            "NOPAT (M)": "¥{:,.0f}M",
                        }
                    ),
                    use_container_width=True,
                )

            # Tab 4: ベンチマーク分析
            with roic_tabs[3]:
                st.subheader("🎯 競合ベンチマーク比較")
                st.markdown("""
    対象企業と業界ベスト企業のROIC・NOPAT Margin・IC Turnoverを比較し、改善余地の大きい指標を特定します。
    ギャップが大きい指標が**最優先の改善対象**となります。マージンとIC Turnoverのどちらを重点的に改善すべきかを判断する際の起点として活用してください。
                    """)

                # 最高値企業を特定
                best_roic = df_tree.loc[df_tree["ROIC (%)"].idxmax()]
                best_margin = df_tree.loc[df_tree["NOPAT Margin (%)"].idxmax()]
                best_turnover = df_tree.loc[df_tree["IC Turnover (x)"].idxmax()]

                col1, col2, col3 = st.columns(3)
                col1.metric(
                    "🏆 Best ROIC",
                    f"{best_roic['ROIC (%)']:.2f}%",
                    f"{best_roic['Company']}",
                )
                col2.metric(
                    "💰 Best Margin",
                    f"{best_margin['NOPAT Margin (%)']:.2f}%",
                    f"{best_margin['Company']}",
                )
                col3.metric(
                    "⚡ Best Turnover",
                    f"{best_turnover['IC Turnover (x)']:.2f}x",
                    f"{best_turnover['Company']}",
                )

                # ギャップ分析（対象企業 vs ベスト）
                target_company = list(DYNAMIC_COMPANIES.keys())[0]
                if target_company in df_tree["Company"].values:
                    target_data = df_tree[
                        df_tree["Company"] == target_company
                    ].iloc[0]

                    st.markdown(f"### 📊 {target_company} のギャップ分析")

                    gap_data = pd.DataFrame(
                        {
                            "メトリクス": ["ROIC", "NOPAT Margin", "IC Turnover"],
                            "現状": [
                                f"{target_data['ROIC (%)']:.2f}%",
                                f"{target_data['NOPAT Margin (%)']:.2f}%",
                                f"{target_data['IC Turnover (x)']:.2f}x",
                            ],
                            "業界ベスト": [
                                f"{best_roic['ROIC (%)']:.2f}%",
                                f"{best_margin['NOPAT Margin (%)']:.2f}%",
                                f"{best_turnover['IC Turnover (x)']:.2f}x",
                            ],
                            "ギャップ": [
                                f"{best_roic['ROIC (%)'] - target_data['ROIC (%)']:.2f}%",
                                f"{best_margin['NOPAT Margin (%)'] - target_data['NOPAT Margin (%)']:.2f}%",
                                f"{best_turnover['IC Turnover (x)'] - target_data['IC Turnover (x)']:.2f}x",
                            ],
                            "改善率": [
                                # #10: 現状値が0の場合でもギャップから改善率を計算
                                f"{((best_roic['ROIC (%)'] / target_data['ROIC (%)']) - 1) * 100:.1f}%"
                                if target_data["ROIC (%)"] > 0
                                else (
                                    "黒字化が必要"
                                    if best_roic["ROIC (%)"] > 0
                                    else "N/A"
                                ),
                                f"{((best_margin['NOPAT Margin (%)'] / target_data['NOPAT Margin (%)']) - 1) * 100:.1f}%"
                                if target_data["NOPAT Margin (%)"] > 0
                                else (
                                    "黒字化が必要"
                                    if best_margin["NOPAT Margin (%)"] > 0
                                    else "N/A"
                                ),
                                f"{((best_turnover['IC Turnover (x)'] / target_data['IC Turnover (x)']) - 1) * 100:.1f}%"
                                if target_data["IC Turnover (x)"] > 0
                                else (
                                    "回転改善が必要"
                                    if best_turnover["IC Turnover (x)"] > 0
                                    else "N/A"
                                ),
                            ],
                        }
                    )

                    st.table(gap_data)

                    st.info(f"""
                    💡 **Consultant's Insight:**
                    {target_company}が業界トップレベルのROICを達成するためには、{best_roic["Company"]}をベンチマークとして設定することが有効です。
                    特にNOPATマージンのギャップが顕著であり、原価構造の見直しとプライシング戦略の再検討が優先課題と考えられます。
                    NOPAT Marginの改善が困難な場合は、IC Turnoverの向上（運転資本圧縮・不要資産の売却）を通じたROIC改善も有効なアプローチです。
                    """)
            # Tab 5: ROIC改善シミュレーション
            with roic_tabs[4]:
                st.subheader("🚀 ROIC改善シミュレーション (DuPont Decomposition)")
                st.markdown("""
    ROIC = **NOPAT Margin × IC Turnover** の関係式を用いて、目標ROICを達成するために必要な改善量を逆算します。
    スライダーで各ドライバーの改善幅を設定し、インパクトをリアルタイムで確認してください。
                    """)

                # 対象企業の現状値を取得
                roic_sim_target_company = list(DYNAMIC_COMPANIES.keys())[0]
                if roic_sim_target_company in df_tree["Company"].values:
                    roic_sim_base = df_tree[
                        df_tree["Company"] == roic_sim_target_company
                    ].iloc[0]
                    roic_sim_current_roic = roic_sim_base["ROIC (%)"]
                    roic_sim_current_margin = roic_sim_base["NOPAT Margin (%)"]
                    roic_sim_current_turnover = roic_sim_base["IC Turnover (x)"]
                    roic_sim_current_revenue_m = roic_sim_base["Revenue (M)"]
                    roic_sim_base["NOPAT (M)"]
                else:
                    # フォールバック: df_treeの最初の行を使用
                    roic_sim_base = df_tree.iloc[0]
                    roic_sim_current_roic = roic_sim_base["ROIC (%)"]
                    roic_sim_current_margin = roic_sim_base["NOPAT Margin (%)"]
                    roic_sim_current_turnover = roic_sim_base["IC Turnover (x)"]
                    roic_sim_current_revenue_m = roic_sim_base["Revenue (M)"]
                    roic_sim_base["NOPAT (M)"]
                    roic_sim_target_company = roic_sim_base["Company"]

                # 投下資本 (IC) を逆算: IC = Revenue / IC_Turnover
                roic_sim_current_ic_m = (
                    roic_sim_current_revenue_m / roic_sim_current_turnover
                    if roic_sim_current_turnover > 0
                    else roic_sim_current_revenue_m
                )

                # CCC現状値の取得（財務データから）
                try:
                    _rs_is, _rs_bs = load_financial_data(target_ticker)
                    if not _rs_is.empty and not _rs_bs.empty:
                        _rs_y = _rs_is.columns[0]
                        _rs_rev = get_val_safe(
                            _rs_is, ["Total Revenue", "Operating Revenue"], _rs_y
                        )
                        _rs_cogs = get_val_safe(
                            _rs_is, ["Cost Of Revenue", "Cost of Goods Sold"], _rs_y
                        )
                        _rs_inv = get_val_safe(_rs_bs, ["Inventory"], _rs_y)
                        _rs_rec = get_val_safe(
                            _rs_bs, ["Accounts Receivable", "Receivables"], _rs_y
                        )
                        _rs_pay = get_val_safe(
                            _rs_bs, ["Accounts Payable", "Payables"], _rs_y
                        )
                        roic_sim_current_dio = (
                            (_rs_inv / _rs_cogs * DAYS_PER_YEAR)
                            if _rs_cogs > 0
                            else 60.0
                        )
                        roic_sim_current_dso = (
                            (_rs_rec / _rs_rev * DAYS_PER_YEAR)
                            if _rs_rev > 0
                            else 45.0
                        )
                        roic_sim_current_dpo = (
                            (_rs_pay / _rs_cogs * DAYS_PER_YEAR)
                            if _rs_cogs > 0
                            else 30.0
                        )
                        roic_sim_cogs_ratio = (
                            (_rs_cogs / _rs_rev) if _rs_rev > 0 else 0.6
                        )
                    else:
                        raise ValueError("empty")
                except (ConnectionError, KeyError, ValueError):
                    (
                        roic_sim_current_dio,
                        roic_sim_current_dso,
                        roic_sim_current_dpo,
                    ) = (
                        60.0,
                        45.0,
                        30.0,
                    )
                    roic_sim_cogs_ratio = 0.6
                roic_sim_current_ccc = (
                    roic_sim_current_dio
                    + roic_sim_current_dso
                    - roic_sim_current_dpo
                )

                # --- 現状値表示 ---
                st.markdown(f"#### 📌 {roic_sim_target_company} の現状値")
                col_base1, col_base2, col_base3, col_base4, col_base5 = st.columns(
                    5
                )
                col_base1.metric("現状 ROIC (%)", f"{roic_sim_current_roic:.2f}%")
                col_base2.metric(
                    "現状 NOPAT Margin (%)", f"{roic_sim_current_margin:.2f}%"
                )
                col_base3.metric(
                    "現状 IC Turnover (x)", f"{roic_sim_current_turnover:.2f}x"
                )
                col_base4.metric("現状 CCC (日)", f"{roic_sim_current_ccc:.0f}日")
                col_base5.metric(
                    "現状 投下資本 (M)", f"{roic_sim_current_ic_m:,.0f}M"
                )

                st.markdown("---")

                # --- シミュレーションパラメータ ---
                st.markdown("#### 🎛️ 改善パラメータ設定")

                col_slider1, col_slider2, col_slider3 = st.columns(3)
                with col_slider1:
                    roic_sim_margin_delta = st.slider(
                        "NOPAT Margin 改善幅 (pp)　※プラス＝改善",
                        min_value=-5.0,
                        max_value=15.0,
                        value=0.0,
                        step=0.5,
                        key="roic_sim_margin_delta",
                        help="原価削減・プライシング改善によるマージン向上",
                    )
                with col_slider2:
                    roic_sim_turnover_delta = st.slider(
                        "IC Turnover 直接改善幅 (x)　※プラス＝改善",
                        min_value=-1.0,
                        max_value=3.0,
                        value=0.0,
                        step=0.1,
                        key="roic_sim_turnover_delta",
                        help="資産売却・設備稼働率向上など、CCC以外の資本効率改善",
                    )
                with col_slider3:
                    roic_sim_ccc_delta = st.slider(
                        "CCC 短縮幅 (日)　※プラス＝短縮（改善）",
                        min_value=0,
                        max_value=int(max(30, roic_sim_current_ccc * 0.8)),
                        value=0,
                        step=5,
                        key="roic_sim_ccc_delta",
                        help="DIO削減・DSO短縮・DPO延長によるCCC改善。投下資本の削減を通じてIC Turnoverを向上させます",
                    )

                # --- CCC → IC Turnover 変換計算 ---
                # CCC短縮 → 運転資本削減量 (M) = (CCC短縮日数 / 365) × 売上高 × COGS比率
                roic_sim_wc_reduction_m = (
                    (roic_sim_ccc_delta / DAYS_PER_YEAR)
                    * roic_sim_current_revenue_m
                    * roic_sim_cogs_ratio
                )
                # 新IC = 現状IC - 運転資本削減量
                roic_sim_new_ic_m = max(
                    roic_sim_current_ic_m * 0.1,
                    roic_sim_current_ic_m - roic_sim_wc_reduction_m,
                )
                # CCCによるIC Turnover改善分
                roic_sim_turnover_from_ccc = (
                    roic_sim_current_revenue_m / roic_sim_new_ic_m
                    - roic_sim_current_turnover
                    if roic_sim_new_ic_m > 0
                    else 0.0
                )

                # --- 全ドライバー統合計算 ---
                roic_sim_new_margin = (
                    roic_sim_current_margin + roic_sim_margin_delta
                )
                roic_sim_total_turnover_delta = (
                    roic_sim_turnover_delta + roic_sim_turnover_from_ccc
                )
                roic_sim_new_turnover = max(
                    0.01, roic_sim_current_turnover + roic_sim_total_turnover_delta
                )
                # ROIC(%) = NOPAT_Margin(%) × IC_Turnover(x) / 100
                roic_sim_new_roic = roic_sim_new_margin * roic_sim_new_turnover

                roic_sim_delta_roic = roic_sim_new_roic - roic_sim_current_roic
                wacc_line = WACC_BENCHMARK * 100  # %表示

                # --- 結果メトリクス ---
                st.markdown("---")
                st.markdown("#### 📊 シミュレーション結果")

                col_res1, col_res2, col_res3, col_res4, col_res5 = st.columns(5)
                col_res1.metric(
                    "シミュレーション ROIC (%)",
                    f"{roic_sim_new_roic:.2f}%",
                    f"{roic_sim_delta_roic:+.2f}pp",
                )
                col_res2.metric(
                    "NOPAT Margin (%)",
                    f"{roic_sim_new_margin:.2f}%",
                    f"{roic_sim_margin_delta:+.2f}pp",
                )
                col_res3.metric(
                    "IC Turnover (x)",
                    f"{roic_sim_new_turnover:.2f}x",
                    f"{roic_sim_total_turnover_delta:+.2f}x",
                )
                col_res4.metric(
                    "CCC (日)",
                    f"{roic_sim_current_ccc - roic_sim_ccc_delta:.0f}日",
                    f"{-roic_sim_ccc_delta:+.0f}日",
                    help="短縮=マイナス=改善",
                )
                col_res5.metric(
                    "運転資本削減 (M)",
                    f"{roic_sim_wc_reduction_m:,.1f}M",
                    help="CCC短縮による投下資本の解放額",
                )

                # WACC超過判定
                wacc_gap = roic_sim_new_roic - wacc_line
                if roic_sim_new_roic >= wacc_line:
                    st.success(
                        f"✅ シミュレーション後のROIC ({roic_sim_new_roic:.2f}%) はWACC ({wacc_line:.1f}%) を上回り、**価値創造ゾーン**に到達しています。対WACCスプレッド: {wacc_gap:+.2f}pp"
                    )
                else:
                    st.warning(
                        f"⚠️ シミュレーション後のROIC ({roic_sim_new_roic:.2f}%) はWACC ({wacc_line:.1f}%) 下回っています。さらなる改善が必要です。対WACCスプレッド: {wacc_gap:+.2f}pp"
                    )

                st.markdown("---")

                # --- ウォーターフォールチャート ---
                st.markdown("#### 📉 ROIC改善ブリッジ分析")

                margin_contribution = (
                    roic_sim_margin_delta * roic_sim_current_turnover
                )
                ccc_turnover_contribution = (
                    roic_sim_turnover_from_ccc * roic_sim_new_margin
                )
                direct_turnover_contribution = (
                    roic_sim_turnover_delta * roic_sim_new_margin
                )
                interaction_effect = (
                    roic_sim_new_roic
                    - roic_sim_current_roic
                    - margin_contribution
                    - ccc_turnover_contribution
                    - direct_turnover_contribution
                )

                bridge_measures = [
                    "absolute",
                    "relative",
                    "relative",
                    "relative",
                    "relative",
                    "total",
                ]
                bridge_x = [
                    "現状 ROIC",
                    "マージン改善効果",
                    "CCC短縮効果\n(IC Turnover↑)",
                    "資産効率\n直接改善効果",
                    "交差効果",
                    "シミュレーション後\nROIC",
                ]
                bridge_y = [
                    roic_sim_current_roic,
                    margin_contribution,
                    ccc_turnover_contribution,
                    direct_turnover_contribution,
                    interaction_effect,
                    roic_sim_new_roic,
                ]
                bridge_text = [
                    f"{roic_sim_current_roic:.2f}%",
                    f"{margin_contribution:+.2f}pp",
                    f"{ccc_turnover_contribution:+.2f}pp",
                    f"{direct_turnover_contribution:+.2f}pp",
                    f"{interaction_effect:+.2f}pp",
                    f"{roic_sim_new_roic:.2f}%",
                ]

                fig_roic_bridge = go.Figure(
                    go.Waterfall(
                        name="ROIC",
                        orientation="v",
                        measure=bridge_measures,
                        x=bridge_x,
                        y=bridge_y,
                        textposition="outside",
                        text=bridge_text,
                        connector={"line": {"color": "rgb(63, 63, 63)"}},
                        increasing={"marker": {"color": "#2ca02c"}},
                        decreasing={"marker": {"color": "#d62728"}},
                        totals={"marker": {"color": "#1f77b4"}},
                    )
                )
                fig_roic_bridge.add_hline(
                    y=wacc_line,
                    line_dash="dash",
                    line_color="red",
                    annotation_text=f"WACC ({wacc_line:.1f}%)",
                )
                fig_roic_bridge.update_layout(
                    title="ROIC改善の要因分解（マージン効果 / CCC短縮効果 / 資産効率効果）",
                    yaxis_title="ROIC (%)",
                    template="plotly_white",
                    height=460,
                )
                st.plotly_chart(fig_roic_bridge, use_container_width=True)

                # --- CCC短縮の連鎖メカニズム説明 ---
                if roic_sim_ccc_delta > 0:
                    st.info(f"""
    **🔗 CCC短縮 → ROIC改善の連鎖メカニズム（今回のシミュレーション）:**
    CCC {roic_sim_current_ccc:.0f}日 → {roic_sim_current_ccc - roic_sim_ccc_delta:.0f}日（**{roic_sim_ccc_delta}日短縮**）
    → 運転資本 **{roic_sim_wc_reduction_m:,.1f}M 削減**
    → 投下資本 {roic_sim_current_ic_m:,.0f}M → {roic_sim_new_ic_m:,.0f}M（**{roic_sim_current_ic_m - roic_sim_new_ic_m:,.1f}M 圧縮**）
    → IC Turnover {roic_sim_current_turnover:.2f}x → {roic_sim_new_turnover:.2f}x（**+{roic_sim_turnover_from_ccc:.2f}x 向上**）
    → ROIC **+{ccc_turnover_contribution:.2f}pp 改善**
                        """)

                # --- 感応度ヒートマップ ---
                st.markdown("---")
                st.markdown(
                    "#### 🗺️ 感応度マトリクス（NOPAT Margin × IC Turnover → ROIC）"
                )
                st.markdown(
                    "各セルの数値は、そのマージン・回転率の組み合わせにおける**予測ROIC(%)**を示します。緑が高いほど資本効率が高い状態を意味します。"
                )

                margin_range = np.arange(
                    max(0.5, roic_sim_current_margin - 4),
                    roic_sim_current_margin + 8.5,
                    2.0,
                )
                turnover_range = np.arange(
                    max(0.1, roic_sim_current_turnover - 0.8),
                    roic_sim_current_turnover + 1.7,
                    0.4,
                )

                heat_data = []
                for m in margin_range:
                    row = []
                    for t in turnover_range:
                        row.append(round(m * t, 2))
                    heat_data.append(row)

                fig_heatmap = go.Figure(
                    data=go.Heatmap(
                        z=heat_data,
                        x=[f"{t:.1f}x" for t in turnover_range],
                        y=[f"{m:.1f}%" for m in margin_range],
                        colorscale="RdYlGn",
                        text=[[f"{v:.1f}%" for v in row] for row in heat_data],
                        texttemplate="%{text}",
                        textfont={"size": 11},
                        colorbar={"title": "ROIC (%)"},
                    )
                )

                # 現状位置をマーク
                closest_margin_idx = int(
                    np.argmin(np.abs(margin_range - roic_sim_current_margin))
                )
                closest_turnover_idx = int(
                    np.argmin(np.abs(turnover_range - roic_sim_current_turnover))
                )
                fig_heatmap.add_annotation(
                    x=f"{turnover_range[closest_turnover_idx]:.1f}x",
                    y=f"{margin_range[closest_margin_idx]:.1f}%",
                    text="◉ 現状",
                    showarrow=False,
                    font={"color": "black", "size": 13, "family": "Arial Bold"},
                )

                fig_heatmap.update_layout(
                    title="ROIC感応度マトリクス（行: NOPAT Margin / 列: IC Turnover）",
                    xaxis_title="IC Turnover (x)",
                    yaxis_title="NOPAT Margin (%)",
                    template="plotly_white",
                    height=420,
                )
                st.plotly_chart(fig_heatmap, use_container_width=True)

                # --- 3つの改善パス逆算 ---
                st.markdown("---")
                st.markdown("#### 🗺️ 目標ROIC達成に向けた改善パス")

                roic_sim_target_roic = st.slider(
                    "目標ROIC (%)",
                    min_value=1.0,
                    max_value=30.0,
                    value=max(wacc_line, roic_sim_current_roic + 2.0),
                    step=0.5,
                    key="roic_sim_target_roic",
                    help="達成したい目標ROICを設定してください",
                )

                if (
                    roic_sim_current_roic > 0
                    and roic_sim_current_margin > 0
                    and roic_sim_current_turnover > 0
                ):
                    # パス①: マージンのみ改善
                    # target_roic(%) = new_margin(%) × current_turnover
                    path1_margin_needed = (
                        roic_sim_target_roic / roic_sim_current_turnover
                        if roic_sim_current_turnover > 0
                        else roic_sim_current_margin
                    )
                    path1_margin_delta = (
                        path1_margin_needed - roic_sim_current_margin
                    )

                    # パス②: IC Turnoverのみ改善
                    # target_roic(%) = current_margin(%) × new_turnover
                    path2_turnover_needed = (
                        roic_sim_target_roic / roic_sim_current_margin
                        if roic_sim_current_margin > 0
                        else roic_sim_current_turnover
                    )
                    path2_turnover_delta = (
                        path2_turnover_needed - roic_sim_current_turnover
                    )

                    # パス③: 両方均等改善（比率で按分）
                    # target = (margin_pct + dm) × (turnover + dt) を均等スケールで解く
                    scale_factor = (
                        (roic_sim_target_roic / roic_sim_current_roic) ** 0.5
                        if roic_sim_current_roic > 0
                        else 1.0
                    )
                    path3_margin_needed = roic_sim_current_margin * scale_factor
                    path3_turnover_needed = roic_sim_current_turnover * scale_factor
                    path3_margin_delta = (
                        path3_margin_needed - roic_sim_current_margin
                    )
                    path3_turnover_delta = (
                        path3_turnover_needed - roic_sim_current_turnover
                    )

                    path_df = pd.DataFrame(
                        {
                            "改善パス": [
                                "パス①: NOPATマージンのみ改善",
                                "パス②: IC Turnoverのみ改善",
                                "パス③: 両方バランス改善",
                            ],
                            "目標NOPAT Margin (%)": [
                                f"{path1_margin_needed:.2f}%",
                                f"{roic_sim_current_margin:.2f}% (変更なし)",
                                f"{path3_margin_needed:.2f}%",
                            ],
                            "必要改善幅 (Margin)": [
                                f"{path1_margin_delta:+.2f}pp",
                                "—",
                                f"{path3_margin_delta:+.2f}pp",
                            ],
                            "目標IC Turnover (x)": [
                                f"{roic_sim_current_turnover:.2f}x (変更なし)",
                                f"{path2_turnover_needed:.2f}x",
                                f"{path3_turnover_needed:.2f}x",
                            ],
                            "必要改善幅 (Turnover)": [
                                "—",
                                f"{path2_turnover_delta:+.2f}x",
                                f"{path3_turnover_delta:+.2f}x",
                            ],
                            "達成ROIC (%)": [
                                f"{roic_sim_target_roic:.2f}%",
                                f"{roic_sim_target_roic:.2f}%",
                                f"{path3_margin_needed * path3_turnover_needed:.2f}%",
                            ],
                        }
                    )
                    st.table(path_df)

                    # 改善施策テキスト
                    st.markdown("#### 💼 改善施策の方向性")
                    col_action1, col_action2 = st.columns(2)
                    with col_action1:
                        st.markdown(f"""
    **💰 NOPATマージン改善策** (目標: {path3_margin_needed:.1f}% / 現状: {roic_sim_current_margin:.1f}%)

    - 製品ミックスの高付加価値化・プライシング見直し
    - 原材料調達コスト削減（サプライヤー交渉・代替調達）
    - 固定費の構造的圧縮（拠点統廃合・間接費削減）
    - 生産効率改善による製造原価率の低減
                            """)
                    with col_action2:
                        st.markdown(f"""
    **⚡ IC Turnover改善策** (目標: {path3_turnover_needed:.1f}x / 現状: {roic_sim_current_turnover:.1f}x)

    - 低採算・遊休資産の売却・リースバック
    - 設備稼働率の向上による資産効率改善
    - 成長性の低い事業への投下資本の配分見直し
                            """)

                    col_action3 = st.columns(1)[0]
                    with col_action3:
                        ccc_target = roic_sim_current_ccc * (1 - 0.2)  # 20%短縮例
                        ccc_wc_effect = (
                            ((roic_sim_current_ccc - ccc_target) / DAYS_PER_YEAR)
                            * roic_sim_current_revenue_m
                            * roic_sim_cogs_ratio
                        )
                        st.markdown(f"""
    **🔄 CCC短縮によるIC Turnover改善策** (現状CCC: {roic_sim_current_ccc:.0f}日)

    CCC短縮は運転資本を削減し、投下資本を圧縮することで**IC Turnoverを直接向上**させます。
    20%短縮（{roic_sim_current_ccc:.0f}日 → {ccc_target:.0f}日）の場合、**約{ccc_wc_effect:,.0f}Mの資本解放**が見込まれます。

    | 施策 | 効果 | 具体例 |
    |------|------|--------|
    | **DIO削減** | 在庫圧縮 → IC減少 | S&OP高度化、サプライヤー小ロット化 |
    | **DSO短縮** | 売掛金回収加速 → IC減少 | 早期払い割引、与信管理強化 |
    | **DPO延長** | 支払サイト延長 → IC減少 | 仕入条件の見直し、支払タイミング最適化 |
                            """)

        else:
            st.warning(
                "ROICツリーデータが取得できませんでした。企業・ティッカーを確認してください。"
            )
    except (KeyError, ValueError, TypeError) as e:
        st.error(f"ROICツリーの描画中にエラーが発生しました: {e}")
