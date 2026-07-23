import streamlit as st

from .detail_ccc import render_ccc_analysis
from .detail_financial_trends import render_financial_trends
from .detail_roic_tree import render_roic_tree


def render_detail_analysis(
    target_ticker,
    target_company_name,
    DYNAMIC_COMPANIES,
    DYNAMIC_COLORS,
    load_financial_data,
    calculate_financial_metrics,
    calculate_ccc_metrics,
    get_val_safe,
    load_markdown_asset,
    ensure_historical_marginal_profit_data,
    load_marginal_profit_data,
    DAYS_PER_YEAR=365,
    WACC_BENCHMARK=0.05,
    ANIMATION_DURATION_MS=2500,
    ANIMATION_TRANSITION_MS=1500,
):
    """
    メインタブ 2: 🌳 詳細収益・効率分析 (Detail Analysis) のレンダリング
    """
    sub_tab2_1, sub_tab2_2, sub_tab2_3 = st.tabs(
        ["📉 財務推移分析", "🌳 ROICツリー分析", "🔄 CCC・運転資本詳細"]
    )

    with sub_tab2_1:
        render_financial_trends(
            target_ticker=target_ticker,
            target_company_name=target_company_name,
            load_financial_data=load_financial_data,
            get_val_safe=get_val_safe,
            ensure_historical_marginal_profit_data=ensure_historical_marginal_profit_data,
            load_marginal_profit_data=load_marginal_profit_data,
            ANIMATION_DURATION_MS=ANIMATION_DURATION_MS,
            ANIMATION_TRANSITION_MS=ANIMATION_TRANSITION_MS,
        )

    with sub_tab2_2:
        render_roic_tree(
            target_ticker=target_ticker,
            DYNAMIC_COMPANIES=DYNAMIC_COMPANIES,
            DYNAMIC_COLORS=DYNAMIC_COLORS,
            load_financial_data=load_financial_data,
            calculate_financial_metrics=calculate_financial_metrics,
            get_val_safe=get_val_safe,
            load_markdown_asset=load_markdown_asset,
            DAYS_PER_YEAR=DAYS_PER_YEAR,
            WACC_BENCHMARK=WACC_BENCHMARK,
        )

    with sub_tab2_3:
        render_ccc_analysis(
            target_company_name=target_company_name,
            DYNAMIC_COMPANIES=DYNAMIC_COMPANIES,
            load_financial_data=load_financial_data,
            calculate_ccc_metrics=calculate_ccc_metrics,
            load_markdown_asset=load_markdown_asset,
        )
