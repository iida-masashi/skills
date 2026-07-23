from typing import Any


def calculate_simulated_financials(
    current_revenue: float,
    current_cogs_ratio: float,  # In percentage, e.g., 65.0 for 65%
    current_opex_ratio: float,  # In percentage
    current_dio: float,
    current_dso: float,
    current_dpo: float,
    current_capex: float,
    current_ocf: float,
    revenue_growth_pct: float = 0.0,
    cogs_change_pp: float = 0.0,
    opex_change_pp: float = 0.0,
    dio_change_days: float = 0.0,
    dso_change_days: float = 0.0,
    dpo_change_days: float = 0.0,
    capex_change_pct: float = 0.0,
    capex_efficiency: float = 1.5,
) -> dict[str, Any]:
    """
    シミュレーションパラメータから未来の財務指標を計算する共通ロジック
    """
    # 収益性の計算
    sim_revenue_base = current_revenue * (1 + revenue_growth_pct / 100.0)
    sim_cogs_ratio = current_cogs_ratio + cogs_change_pp
    sim_opex_ratio = current_opex_ratio + opex_change_pp

    # 投資戦略に基づく売上追加効果の計算
    sim_capex = current_capex * (1 + capex_change_pct / 100.0)
    capex_driven_revenue_growth = (sim_capex - current_capex) * capex_efficiency

    # 統合売上高
    total_sim_revenue = sim_revenue_base + capex_driven_revenue_growth

    # コスト・利益計算
    sim_cogs = total_sim_revenue * (sim_cogs_ratio / 100.0)
    sim_opex = total_sim_revenue * (sim_opex_ratio / 100.0)
    sim_oi = total_sim_revenue - sim_cogs - sim_opex
    sim_oi_margin = (
        (sim_oi / total_sim_revenue * 100.0) if total_sim_revenue > 0 else 0.0
    )

    # 運転資本・CCC計算
    sim_dio = max(0.0, current_dio + dio_change_days)
    sim_dso = max(0.0, current_dso + dso_change_days)
    sim_dpo = max(0.0, current_dpo + dpo_change_days)
    sim_ccc = sim_dio + sim_dso - sim_dpo

    # キャッシュフロー計算
    # 簡易化のため、OCFは売上成長率に比例すると仮定
    sim_ocf = current_ocf * (1 + revenue_growth_pct / 100.0)
    sim_fcf = sim_ocf - sim_capex

    return {
        "revenue": total_sim_revenue,
        "cogs": sim_cogs,
        "opex": sim_opex,
        "operating_income": sim_oi,
        "operating_margin": sim_oi_margin,
        "dio": sim_dio,
        "dso": sim_dso,
        "dpo": sim_dpo,
        "ccc": sim_ccc,
        "capex": sim_capex,
        "ocf": sim_ocf,
        "fcf": sim_fcf,
    }
