import streamlit as st

from consultant_toolkit.ui_components.ui_helpers import load_base_financials


def render_demand_forecast(
    target_ticker,
    load_financial_data,
    get_val_safe,
    DAYS_PER_YEAR=365,
):
    """
    サブタブ 3.2: 需要予測・在庫削減シミュレーション (Forecast Accuracy Impact)
    """
    st.header(
        "3.2 🔮 需要予測・在庫削減シミュレーション (Forecast Accuracy Impact)"
    )
    st.markdown(
        "「需要予測精度の向上が、適正在庫の削減および営業利益の向上にどれほどのインパクトを与えるかをシミュレーションします。」"
    )

    fin = load_base_financials(target_ticker, load_financial_data, get_val_safe)
    if not fin.has_real_data:
        st.warning("財務データの取得に失敗しました。デフォルト値を使用します。")

    current_revenue = fin.revenue
    current_oi = fin.operating_income
    current_oi_margin = fin.oi_margin
    current_inventory = fin.inventory

    st.subheader("🎛️ シミュレーション パラメータ")

    col_fc1, col_fc2 = st.columns(2)
    with col_fc1:
        forecast_improvement = st.slider(
            "需要予測精度の向上率 (%)",
            min_value=0.0,
            max_value=20.0,
            value=5.0,
            step=0.5,
            help="AI需要予測などを導入したことによる予測精度の向上幅を設定します。",
        )
    with col_fc2:
        inventory_reduction_multiplier = st.slider(
            "予測向上1%あたりの在庫削減率 (%)",
            min_value=0.1,
            max_value=2.0,
            value=0.5,
            step=0.1,
            help="予測精度が1%向上した際に、安全在庫などが何%削減できるかの係数です。（通常0.5〜1.0）",
        )

    holding_cost_rate = st.slider(
        "在庫保管コスト率 (%)",
        min_value=5.0,
        max_value=30.0,
        value=15.0,
        step=1.0,
        help="在庫を維持するための年間コスト率（倉庫代、陳腐化、資本コスト等）。通常15%〜25%程度。",
    )

    # ロジック計算
    inventory_reduction_pct = forecast_improvement * inventory_reduction_multiplier
    sim_inventory = current_inventory * (1 - inventory_reduction_pct / 100)
    inventory_reduction_amount = current_inventory - sim_inventory

    # 在庫が減ることによる保管コストの削減 = 営業利益へのダイレクトなプラス
    cost_savings = inventory_reduction_amount * (holding_cost_rate / 100)

    sim_oi = current_oi + cost_savings
    sim_oi_margin = (sim_oi / current_revenue * 100) if current_revenue > 0 else 0

    st.markdown("---")
    st.subheader("📊 シミュレーション結果")

    col_res_fc1, col_res_fc2, col_res_fc3, col_res_fc4 = st.columns(4)
    with col_res_fc1:
        st.metric(
            "在庫削減率",
            f"{inventory_reduction_pct:.1f}%",
            f"予測精度 +{forecast_improvement:.1f}%",
        )
    with col_res_fc2:
        st.metric(
            "在庫金額 (M)",
            f"{sim_inventory / 1e6:,.1f} M",
            f"{-inventory_reduction_amount / 1e6:,.1f} M (削減額)",
        )
    with col_res_fc3:
        st.metric(
            "営業利益 (M)",
            f"{sim_oi / 1e6:,.1f} M",
            f"+{cost_savings / 1e6:,.1f} M (コスト削減)",
        )
    with col_res_fc4:
        st.metric(
            "営業利益率 (%)",
            f"{sim_oi_margin:.2f}%",
            f"+{(sim_oi_margin - current_oi_margin):.2f} pp",
        )

    st.info(
        f"💡 **Consultant's Insight:**\n\n"
        f"需要予測精度が **{forecast_improvement:.1f}%** 向上することで、在庫金額が **{inventory_reduction_amount / 1e6:,.1f}M** 削減され、"
        f"結果として在庫保管コストが下がり、営業利益が **{cost_savings / 1e6:,.1f}M** 増加します。営業利益率は **{(sim_oi_margin - current_oi_margin):.2f}pp** の改善が見込まれます。"
    )
