import streamlit as st

from consultant_toolkit.ui_components.future_ai_strategy import render_ai_strategy
from consultant_toolkit.ui_components.future_capex import render_capex_analysis
from consultant_toolkit.ui_components.future_demand_forecast import (
    render_demand_forecast,
)
from consultant_toolkit.ui_components.future_whatif import render_whatif_simulator


def render_future_simulation(
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
    DAYS_PER_YEAR=365,
    WACC_BENCHMARK=0.05,
    ANIMATION_DURATION_MS=2500,
    ANIMATION_TRANSITION_MS=1500,
):
    """
    メインタブ 3: 🏗️ 投資・将来予測 (Future & Simulation) のレンダリング
    """
    sub_tab3_1, sub_tab3_2, sub_tab3_3, sub_tab3_4 = st.tabs(
        [
            "🎰 What-If シミュレーター",
            "🔮 需要予測Sim",
            "💸 投資効率(CAPEX)",
            "🤖 AI戦略提案",
        ]
    )

    with sub_tab3_1:
        render_whatif_simulator(
            target_ticker=target_ticker,
            target_company_name=target_company_name,
            load_financial_data=load_financial_data,
            get_cashflow_data=get_cashflow_data,
            get_val_safe=get_val_safe,
            DAYS_PER_YEAR=DAYS_PER_YEAR,
        )

    with sub_tab3_2:
        render_demand_forecast(
            target_ticker=target_ticker,
            load_financial_data=load_financial_data,
            get_val_safe=get_val_safe,
            DAYS_PER_YEAR=DAYS_PER_YEAR,
        )

    with sub_tab3_3:
        render_capex_analysis(
            target_ticker=target_ticker,
            target_company_name=target_company_name,
            load_financial_data=load_financial_data,
            get_val_safe=get_val_safe,
        )

    with sub_tab3_4:
        render_ai_strategy(
            target_ticker=target_ticker,
            target_company_name=target_company_name,
            load_financial_data=load_financial_data,
            get_val_safe=get_val_safe,
            DAYS_PER_YEAR=DAYS_PER_YEAR,
        )
