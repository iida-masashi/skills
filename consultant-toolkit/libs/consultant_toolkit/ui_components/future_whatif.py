import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from consultant_toolkit.ui_components.ui_helpers import load_base_financials


def render_whatif_simulator(
    target_ticker,
    target_company_name,
    load_financial_data,
    get_cashflow_data,
    get_val_safe,
    DAYS_PER_YEAR=365,
):
    """
    サブタブ 3.1: What-If シミュレーター (Interactive Financial Simulator)
    """
    st.header("3.1 What-If シミュレーター (Interactive Financial Simulator)")
    st.markdown(
        "「財務指標を動的に調整し、ROIC・FCF・営業利益への影響をリアルタイムで可視化します。経営判断シミュレーションにご活用ください。」"
    )

    # 現在値の取得
    fin = load_base_financials(
        target_ticker,
        load_financial_data,
        get_val_safe,
        get_cashflow_data=get_cashflow_data,
    )
    if not fin.has_real_data:
        st.warning("財務データの取得に失敗しました。デフォルト値を使用します。")

    current_revenue = fin.revenue
    current_cogs_ratio = fin.cogs_ratio
    current_opex_ratio = fin.opex_ratio
    current_oi_margin = fin.oi_margin
    current_oi = fin.operating_income
    current_invested_capital = fin.invested_capital
    current_roic = fin.roic
    current_dio = fin.dio
    current_dso = fin.dso
    current_dpo = fin.dpo
    current_ccc_val = fin.ccc
    current_capex = fin.capex
    current_ocf = fin.ocf
    current_fcf = fin.fcf

    # ===== シミュレーター UI =====
    st.subheader("🎛️ シミュレーション パラメータ")

    # タブで分類（各タブ内にパラメータを配置）
    sim_tabs = st.tabs(
        [
            "💰 収益性改善",
            "🔄 運転資本効率化",
            "🏗️ 投資戦略",
            "📊 総合シミュレーション",
        ]
    )

    # --- タブ1: 収益性改善 ---
    with sim_tabs[0]:
        st.markdown("#### 💰 売上・コスト構造の変更")

        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            revenue_growth = st.slider(
                "売上高 成長率 (%)",
                min_value=-20.0,
                max_value=50.0,
                value=0.0,
                step=1.0,
                key="sim_revenue_growth",
            )
        with col_p2:
            cogs_change = st.slider(
                "売上原価率 変更 (pp)　※マイナス＝改善",
                min_value=-10.0,
                max_value=10.0,
                value=0.0,
                step=0.5,
                key="sim_cogs_change",
            )
        with col_p3:
            opex_change = st.slider(
                "販管費率 変更 (pp)　※マイナス＝改善",
                min_value=-10.0,
                max_value=10.0,
                value=0.0,
                step=0.5,
                key="sim_opex_change",
            )

        # 計算
        sim_revenue = current_revenue * (1 + revenue_growth / 100)
        sim_cogs_ratio = current_cogs_ratio + cogs_change
        sim_opex_ratio = current_opex_ratio + opex_change
        sim_cogs = sim_revenue * (sim_cogs_ratio / 100)
        sim_opex = sim_revenue * (sim_opex_ratio / 100)
        sim_oi = sim_revenue - sim_cogs - sim_opex
        sim_oi_margin = (sim_oi / sim_revenue * 100) if sim_revenue > 0 else 0

        # 現状 vs シミュレーション比較
        st.markdown("---")
        st.markdown("#### 📊 収益性インパクト")

        col_res1, col_res2, col_res3, col_res4 = st.columns(4)

        with col_res1:
            st.metric(
                "売上高 (M)",
                f"{sim_revenue / 1e6:.1f}",
                f"{(sim_revenue - current_revenue) / 1e6:+.1f}",
            )

        with col_res2:
            st.metric(
                "営業利益 (M)",
                f"{sim_oi / 1e6:.1f}",
                f"{(sim_oi - current_oi) / 1e6:+.1f}",
            )

        with col_res3:
            st.metric(
                "営業利益率 (%)",
                f"{sim_oi_margin:.1f}%",
                f"{(sim_oi_margin - current_oi_margin):+.1f}pp",
            )

        with col_res4:
            roic_impact = (sim_oi_margin - current_oi_margin) * 0.5  # 簡易推定
            st.metric(
                "ROIC インパクト (推定)",
                f"{roic_impact:+.1f}pp",
                help="営業利益率改善がROICに与える影響（簡易推定）",
            )

        # ウォーターフォールチャート
        st.markdown("#### 📉 利益ブリッジ分析 (Waterfall Chart)")

        wf_cats = [
            "現状営業利益",
            "売上高増減効果",
            "原価率改善効果",
            "販管費削減効果",
            "シミュレーション後",
        ]
        wf_vals = [
            current_oi / 1e6,
            (sim_revenue - current_revenue) * (current_oi_margin / 100) / 1e6,
            -sim_revenue * (cogs_change / 100) / 1e6,
            -sim_revenue * (opex_change / 100) / 1e6,
            sim_oi / 1e6,
        ]

        fig_waterfall = go.Figure(
            go.Waterfall(
                name="営業利益",
                orientation="v",
                measure=["absolute", "relative", "relative", "relative", "total"],
                x=wf_cats,
                y=wf_vals,
                textposition="outside",
                text=[f"{v:+.1f}M" for v in wf_vals],
                connector={"line": {"color": "rgb(63, 63, 63)"}},
                increasing={"marker": {"color": "#2ca02c"}},
                decreasing={"marker": {"color": "#d62728"}},
                totals={"marker": {"color": "#1f77b4"}},
            )
        )

        fig_waterfall.update_layout(
            title="営業利益の増減要因分解",
            yaxis_title="営業利益 (Million)",
            template="plotly_white",
            height=400,
        )

        st.plotly_chart(fig_waterfall, use_container_width=True)

    # --- タブ2: 運転資本効率化 ---
    with sim_tabs[1]:
        st.markdown("#### 🔄 CCCコンポーネントの最適化")

        col_q1, col_q2, col_q3 = st.columns(3)
        with col_q1:
            dio_change = st.slider(
                "DIO 変更 (日)　※マイナス＝改善",
                min_value=-30,
                max_value=30,
                value=0,
                step=5,
                key="sim_dio_change",
            )
        with col_q2:
            dso_change = st.slider(
                "DSO 変更 (日)　※マイナス＝改善",
                min_value=-20,
                max_value=20,
                value=0,
                step=5,
                key="sim_dso_change",
            )
        with col_q3:
            dpo_change = st.slider(
                "DPO 変更 (日)　※プラス＝改善",
                min_value=-20,
                max_value=20,
                value=0,
                step=5,
                key="sim_dpo_change",
            )

        # 計算
        sim_dio = max(0, current_dio + dio_change)
        sim_dso = max(0, current_dso + dso_change)
        sim_dpo = max(0, current_dpo + dpo_change)
        sim_ccc = sim_dio + sim_dso - sim_dpo
        ccc_improvement = current_ccc_val - sim_ccc

        # CCCインパクト
        st.markdown("---")
        st.markdown("#### 🔄 CCC インパクト")

        col_ccc_res1, col_ccc_res2, col_ccc_res3, col_ccc_res4 = st.columns(4)

        with col_ccc_res1:
            st.metric("DIO (日)", f"{sim_dio:.0f}", f"{dio_change:+.0f}")

        with col_ccc_res2:
            st.metric("DSO (日)", f"{sim_dso:.0f}", f"{dso_change:+.0f}")

        with col_ccc_res3:
            st.metric("DPO (日)", f"{sim_dpo:.0f}", f"{dpo_change:+.0f}")

        with col_ccc_res4:
            st.metric(
                "CCC (日)",
                f"{sim_ccc:.0f}",
                f"{-ccc_improvement:+.0f}",
                help="短縮=マイナス=改善",
            )

        # CCCチャート
        st.markdown("#### 📊 CCC コンポーネント比較")

        fig_ccc_comp = go.Figure()

        fig_ccc_comp.add_trace(
            go.Bar(
                name="現状",
                x=["DIO", "DSO", "DPO", "CCC"],
                y=[current_dio, current_dso, -current_dpo, current_ccc_val],
                marker_color=["#ff7f0e", "#2ca02c", "#d62728", "#1f77b4"],
                text=[
                    f"{current_dio:.0f}日",
                    f"{current_dso:.0f}日",
                    f"{-current_dpo:.0f}日",
                    f"{current_ccc_val:.0f}日",
                ],
                textposition="outside",
            )
        )

        fig_ccc_comp.add_trace(
            go.Bar(
                name="シミュレーション",
                x=["DIO", "DSO", "DPO", "CCC"],
                y=[sim_dio, sim_dso, -sim_dpo, sim_ccc],
                marker_color=["#ff7f0e", "#2ca02c", "#d62728", "#1f77b4"],
                marker_line={"width": 2, "color": "black"},
                opacity=0.7,
                text=[
                    f"{sim_dio:.0f}日",
                    f"{sim_dso:.0f}日",
                    f"{-sim_dpo:.0f}日",
                    f"{sim_ccc:.0f}日",
                ],
                textposition="outside",
            )
        )

        fig_ccc_comp.update_layout(
            title="CCC コンポーネント: 現状 vs シミュレーション",
            yaxis_title="日数",
            template="plotly_white",
            barmode="group",
            height=400,
        )

        st.plotly_chart(fig_ccc_comp, use_container_width=True)

        # 運転資本への影響
        if current_revenue > 0 and current_cogs_ratio > 0:
            working_capital_reduction = (ccc_improvement / DAYS_PER_YEAR) * (
                current_revenue * (current_cogs_ratio / 100)
            )
            st.info(
                f"💡 **運転資本削減効果:** CCC {ccc_improvement:.0f}日短縮により、約 **{working_capital_reduction / 1e6:,.1f}M** の運転資本を削減できます。"
            )

    # --- タブ3: 投資戦略 ---
    with sim_tabs[2]:
        st.markdown("#### 🏗️ CAPEX・投資配分の最適化")

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            capex_change = st.slider(
                "CAPEX 変更率 (%)　※プラス＝増額",
                min_value=-50,
                max_value=100,
                value=0,
                step=10,
                key="sim_capex_change",
            )
        with col_r2:
            capex_efficiency = st.slider(
                "CAPEX効率性（投資1円あたりの売上創出倍率）",
                min_value=0.5,
                max_value=3.0,
                value=1.5,
                step=0.1,
                key="sim_capex_efficiency",
            )

        # 計算
        sim_capex = current_capex * (1 + capex_change / 100)
        capex_driven_revenue_growth = (sim_capex - current_capex) * capex_efficiency
        sim_fcf_investment = current_ocf - sim_capex

        # インパクト
        st.markdown("---")
        st.markdown("#### 🏗️ 投資インパクト")

        col_inv1, col_inv2, col_inv3, col_inv4 = st.columns(4)

        with col_inv1:
            st.metric(
                "CAPEX (M)",
                f"{sim_capex / 1e6:.1f}",
                f"{(sim_capex - current_capex) / 1e6:+.1f}",
            )

        with col_inv2:
            st.metric(
                "FCF (M)",
                f"{sim_fcf_investment / 1e6:.1f}",
                f"{(sim_fcf_investment - current_fcf) / 1e6:+.1f}",
            )

        with col_inv3:
            st.metric(
                "売上増加効果 (M)",
                f"{capex_driven_revenue_growth / 1e6:.1f}",
                help="CAPEX増加による売上成長期待値",
            )

        with col_inv4:
            roi_capex = (
                (capex_driven_revenue_growth / (sim_capex - current_capex) * 100)
                if (sim_capex - current_capex) != 0
                else 0
            )
            st.metric(
                "投資ROI (%)",
                f"{roi_capex:.0f}%",
                help="追加投資1円あたりの売上増加効果",
            )

        # FCFトレンドシミュレーション
        st.markdown("#### 📈 FCF推移シミュレーション (3年間)")

        years_sim = ["Year 0 (現状)", "Year 1", "Year 2", "Year 3"]
        fcf_scenario_conservative = [current_fcf / 1e6]
        fcf_scenario_base = [current_fcf / 1e6]
        fcf_scenario_aggressive = [current_fcf / 1e6]

        for year in range(1, 4):
            # 保守的: OCF成長2%, CAPEX現状維持
            fcf_cons = (current_ocf * (1.02**year) - sim_capex) / 1e6
            fcf_scenario_conservative.append(fcf_cons)

            # ベース: OCF成長5%, CAPEX現状維持
            fcf_base = (current_ocf * (1.05**year) - sim_capex) / 1e6
            fcf_scenario_base.append(fcf_base)

            # 積極的: OCF成長8%, CAPEX増加分も成長寄与
            fcf_aggr = (current_ocf * (1.08**year) - sim_capex * (1.02**year)) / 1e6
            fcf_scenario_aggressive.append(fcf_aggr)

        fig_fcf_sim = go.Figure()

        fig_fcf_sim.add_trace(
            go.Scatter(
                x=years_sim,
                y=fcf_scenario_conservative,
                mode="lines+markers",
                name="保守的 (OCF成長2%)",
                line={"color": "#d62728", "dash": "dot"},
            )
        )

        fig_fcf_sim.add_trace(
            go.Scatter(
                x=years_sim,
                y=fcf_scenario_base,
                mode="lines+markers",
                name="ベース (OCF成長5%)",
                line={"color": "#1f77b4", "width": 3},
            )
        )

        fig_fcf_sim.add_trace(
            go.Scatter(
                x=years_sim,
                y=fcf_scenario_aggressive,
                mode="lines+markers",
                name="積極的 (OCF成長8%)",
                line={"color": "#2ca02c", "dash": "dash"},
            )
        )

        fig_fcf_sim.update_layout(
            title=f"FCF推移シミュレーション (CAPEX変更率: {capex_change:+.0f}%)",
            xaxis_title="期間",
            yaxis_title="FCF (Million)",
            template="plotly_white",
            height=400,
        )

        st.plotly_chart(fig_fcf_sim, use_container_width=True)

    # --- タブ4: 総合シミュレーション ---
    with sim_tabs[3]:
        st.markdown("#### 🎯 総合インパクト分析")
        st.markdown(
            "各タブのパラメータを一括で設定し、全指標への統合インパクトを確認します。"
        )

        with st.expander("🎛️ 全パラメータ設定", expanded=True):
            col_all1, col_all2, col_all3 = st.columns(3)
            with col_all1:
                st.markdown("**💰 収益性**")
                revenue_growth = st.slider(
                    "売上高 成長率 (%)",
                    -20.0,
                    50.0,
                    float(st.session_state.get("sim_revenue_growth", 0.0)),
                    1.0,
                    key="sim_revenue_growth_all",
                )
                cogs_change = st.slider(
                    "売上原価率 変更 (pp)",
                    -10.0,
                    10.0,
                    float(st.session_state.get("sim_cogs_change", 0.0)),
                    0.5,
                    key="sim_cogs_change_all",
                )
                opex_change = st.slider(
                    "販管費率 変更 (pp)",
                    -10.0,
                    10.0,
                    float(st.session_state.get("sim_opex_change", 0.0)),
                    0.5,
                    key="sim_opex_change_all",
                )
            with col_all2:
                st.markdown("**🔄 運転資本**")
                dio_change = st.slider(
                    "DIO 変更 (日)",
                    -30,
                    30,
                    int(st.session_state.get("sim_dio_change", 0)),
                    5,
                    key="sim_dio_change_all",
                )
                dso_change = st.slider(
                    "DSO 変更 (日)",
                    -20,
                    20,
                    int(st.session_state.get("sim_dso_change", 0)),
                    5,
                    key="sim_dso_change_all",
                )
                dpo_change = st.slider(
                    "DPO 変更 (日)",
                    -20,
                    20,
                    int(st.session_state.get("sim_dpo_change", 0)),
                    5,
                    key="sim_dpo_change_all",
                )
            with col_all3:
                st.markdown("**🏗️ 投資**")
                capex_change = st.slider(
                    "CAPEX 変更率 (%)",
                    -50,
                    100,
                    int(st.session_state.get("sim_capex_change", 0)),
                    10,
                    key="sim_capex_change_all",
                )
                capex_efficiency = st.slider(
                    "CAPEX効率性",
                    0.5,
                    3.0,
                    float(st.session_state.get("sim_capex_efficiency", 1.5)),
                    0.1,
                    key="sim_capex_efficiency_all",
                )

        # 全パラメータを再計算（タブ4独立計算）
        sim_revenue = current_revenue * (1 + revenue_growth / 100)
        sim_cogs_ratio = current_cogs_ratio + cogs_change
        sim_opex_ratio = current_opex_ratio + opex_change
        sim_cogs = sim_revenue * (sim_cogs_ratio / 100)
        sim_opex = sim_revenue * (sim_opex_ratio / 100)
        sim_oi = sim_revenue - sim_cogs - sim_opex
        sim_capex = current_capex * (1 + capex_change / 100)
        capex_driven_revenue_growth = (sim_capex - current_capex) * capex_efficiency

        # 全パラメータを統合
        total_revenue_sim = sim_revenue + capex_driven_revenue_growth
        total_oi_sim = (
            total_revenue_sim
            - (total_revenue_sim * sim_cogs_ratio / 100)
            - (total_revenue_sim * sim_opex_ratio / 100)
        )
        total_oi_margin_sim = (
            (total_oi_sim / total_revenue_sim * 100) if total_revenue_sim > 0 else 0
        )

        total_fcf_sim = current_ocf * (1 + revenue_growth / 100) - sim_capex

        # ROICシミュレーション (CCC短縮による投下資本削減効果を考慮)
        sim_dio = max(0, current_dio + dio_change)
        sim_dso = max(0, current_dso + dso_change)
        sim_dpo = max(0, current_dpo + dpo_change)
        sim_ccc = sim_dio + sim_dso - sim_dpo
        ccc_improvement_total = current_ccc_val - sim_ccc
        working_capital_reduction_total = (
            ccc_improvement_total / DAYS_PER_YEAR
        ) * (current_revenue * (current_cogs_ratio / 100))
        sim_invested_capital = max(
            current_invested_capital * 0.1,
            current_invested_capital - working_capital_reduction_total,
        )
        sim_nopat = total_oi_sim * 0.7  # 推定税率30%
        sim_roic = (
            (sim_nopat / sim_invested_capital * 100)
            if sim_invested_capital > 0
            else 0
        )

        # サマリーメトリクス
        st.markdown("#### 📊 統合KPIダッシュボード")

        col_total1, col_total2, col_total3, col_total4, col_total5, col_total6 = (
            st.columns(6)
        )

        with col_total1:
            st.metric(
                "売上高 (M)",
                f"{total_revenue_sim / 1e6:.1f}",
                f"{(total_revenue_sim - current_revenue) / 1e6:+.1f}M",
            )

        with col_total2:
            st.metric(
                "営業利益 (M)",
                f"{total_oi_sim / 1e6:.1f}",
                f"{(total_oi_sim - current_oi) / 1e6:+.1f}M",
            )

        with col_total3:
            st.metric(
                "営業利益率 (%)",
                f"{total_oi_margin_sim:.1f}%",
                f"{(total_oi_margin_sim - current_oi_margin):+.1f}pp",
            )

        with col_total4:
            st.metric(
                "ROIC (%)",
                f"{sim_roic:.2f}%",
                f"{sim_roic - current_roic:+.2f}pp",
                help="税後営業利益(NOPAT) ÷ 投下資本。CCC短縮による運転資本圧縮効果を含みます。",
            )

        with col_total5:
            st.metric(
                "CCC (日)",
                f"{sim_ccc:.0f}",
                f"{(sim_ccc - current_ccc_val):+.0f}日",
            )

        with col_total6:
            st.metric(
                "FCF (M)",
                f"{total_fcf_sim / 1e6:.1f}",
                f"{(total_fcf_sim - current_fcf) / 1e6:+.1f}M",
            )

        # レーダーチャート（現状 vs シミュレーション）
        st.markdown("---")
        st.markdown("#### 🕸️ 総合パフォーマンス比較 (Radar Chart)")

        categories_radar = [
            "収益性",
            "効率性",
            "キャッシュ創出",
            "成長性",
            "投資効率",
            "ROIC",
        ]

        # 現状スコア（正規化: 0-100）
        current_scores = [
            min(current_oi_margin * 5, 100),  # 収益性
            max(0, 100 - current_ccc_val),  # 効率性
            min((current_fcf / current_revenue * 100) * 10, 100)
            if current_revenue > 0
            else 50,  # キャッシュ創出
            50,  # 成長性（ベースライン）
            min((current_ocf / current_capex) * 20, 100)
            if current_capex > 0
            else 50,  # 投資効率
            min(current_roic * 5, 100),  # ROIC (20%で100)
        ]

        # シミュレーションスコア
        sim_scores = [
            min(total_oi_margin_sim * 5, 100),
            max(0, 100 - sim_ccc),
            min((total_fcf_sim / total_revenue_sim * 100) * 10, 100)
            if total_revenue_sim > 0
            else 50,
            min((revenue_growth + 50), 100),  # 成長性
            min((current_ocf / sim_capex) * 20, 100) if sim_capex > 0 else 50,
            min(sim_roic * 5, 100),  # ROIC
        ]

        fig_radar = go.Figure()

        fig_radar.add_trace(
            go.Scatterpolar(
                r=current_scores,
                theta=categories_radar,
                fill="toself",
                name="現状",
                line={"color": "#1f77b4"},
            )
        )

        fig_radar.add_trace(
            go.Scatterpolar(
                r=sim_scores,
                theta=categories_radar,
                fill="toself",
                name="シミュレーション",
                line={"color": "#2ca02c"},
            )
        )

        fig_radar.update_layout(
            polar={"radialaxis": {"visible": True, "range": [0, 100]}},
            title="企業パフォーマンス: 現状 vs シミュレーション",
            template="plotly_white",
            height=500,
        )

        st.plotly_chart(fig_radar, use_container_width=True)

        # アクションプラン生成
        st.markdown("---")
        st.markdown("#### 💼 推奨アクションプラン")

        actions = []

        if cogs_change < -1:
            actions.append(
                f"✅ **原価削減:** 売上原価率を{abs(cogs_change):.1f}pp削減 → 営業利益 {abs(sim_revenue * cogs_change / 100) / 1e6:.1f}M増加"
            )

        if dio_change < -5:
            actions.append(
                f"✅ **在庫最適化:** DIOを{abs(dio_change)}日短縮 → 運転資本 {abs(working_capital_reduction_total) / 1e6:.1f}M削減"
            )

        if sim_roic > current_roic + 0.5:
            actions.append(
                f"🚀 **資本効率向上:** 一連の改善により、ROICが **{sim_roic - current_roic:+.2f}pp** 向上し、企業価値創出力が強化されます。"
            )

        if dso_change < -5:
            actions.append(
                f"✅ **売掛金回収強化:** DSOを{abs(dso_change)}日短縮 → キャッシュフロー改善"
            )

        if capex_change < 0:
            actions.append(
                f"✅ **投資抑制:** CAPEXを{abs(capex_change)}%削減 → FCF {(current_fcf - total_fcf_sim) / 1e6:.1f}M改善"
            )
        elif capex_change > 0:
            actions.append(
                f"✅ **成長投資:** CAPEXを{capex_change}%増加 → 売上成長 {capex_driven_revenue_growth / 1e6:.1f}M期待"
            )

        if actions:
            for action in actions:
                st.markdown(action)
        else:
            st.info(
                "💡 パラメータを調整して、改善施策のインパクトを確認してください。"
            )

        # エクスポート
        st.markdown("---")
        if st.button(
            "📥 シミュレーション結果をエクスポート", use_container_width=True
        ):
            sim_results = {
                "simulation_date": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "company": target_company_name,
                "ticker": target_ticker,
                "parameters": {
                    "revenue_growth": f"{revenue_growth}%",
                    "cogs_change": f"{cogs_change}pp",
                    "opex_change": f"{opex_change}pp",
                    "dio_change": f"{dio_change}日",
                    "dso_change": f"{dso_change}日",
                    "dpo_change": f"{dpo_change}日",
                    "capex_change": f"{capex_change}%",
                },
                "results": {
                    "revenue": f"{total_revenue_sim / 1e6:.1f}M",
                    "operating_income": f"{total_oi_sim / 1e6:.1f}M",
                    "operating_margin": f"{total_oi_margin_sim:.1f}%",
                    "ccc": f"{sim_ccc:.0f}日",
                    "fcf": f"{total_fcf_sim / 1e6:.1f}M",
                },
                "impact": {
                    "revenue_change": f"{(total_revenue_sim - current_revenue) / 1e6:+.1f}M",
                    "oi_change": f"{(total_oi_sim - current_oi) / 1e6:+.1f}M",
                    "ccc_change": f"{(sim_ccc - current_ccc_val):+.0f}日",
                    "fcf_change": f"{(total_fcf_sim - current_fcf) / 1e6:+.1f}M",
                },
            }

            st.json(sim_results)
            st.download_button(
                "💾 JSON形式でダウンロード",
                data=json.dumps(sim_results, indent=2, ensure_ascii=False),
                file_name=f"whatif_simulation_{target_ticker}_{pd.Timestamp.now().strftime('%Y%m%d')}.json",
                mime="application/json",
            )
