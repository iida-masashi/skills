import os

import numpy as np
import polars as pl


def _get_category_base_metrics() -> dict[str, dict[str, float]]:
    """カテゴリ別の基本売上・利益率を返す"""
    return {
        "Standard Fasteners (汎用ファスナー)": {"rev": 55000, "margin": 0.28},
        "Precision Springs (精密ばね)": {"rev": 30000, "margin": 0.30},
        "Air Dampers (エアダンパー)": {"rev": 10000, "margin": 0.38},
        "EV Battery Parts (EV電池部品)": {"rev": 500, "margin": 0.05},
        "Medical Catheters (医療用カテーテル)": {"rev": 1500, "margin": 0.40},
    }


def _get_year_factors(year: int) -> dict[str, float]:
    """年度別のマクロ経済係数と材料費影響を返す"""
    macro_factors = {
        2015: 1.0,
        2016: 1.02,
        2017: 1.05,
        2018: 1.08,
        2019: 1.02,
        2020: 0.85,
        2021: 1.10,
        2022: 0.90,
        2023: 1.05,
        2024: 1.0,
    }
    material_impacts = {
        2015: 0.0,
        2016: 0.0,
        2017: -0.01,
        2018: -0.01,
        2019: -0.02,
        2020: 0.0,
        2021: -0.02,
        2022: -0.05,
        2023: -0.08,
        2024: -0.07,
    }
    return {
        "macro_revenue": macro_factors.get(year, 1.0),
        "material_cost": material_impacts.get(year, 0.0),
    }


def _calculate_category_revenue(
    category: str, base_revenue: float, year: int, macro_factor: float
) -> float:
    """カテゴリと年度に応じた売上を計算"""
    if category in [
        "Standard Fasteners (汎用ファスナー)",
        "Precision Springs (精密ばね)",
    ]:
        return base_revenue * macro_factor * np.random.uniform(0.95, 1.05)
    elif category == "Air Dampers (エアダンパー)":
        growth_rate = 1.0 + (year - 2015) * 0.04
        return base_revenue * growth_rate * np.random.uniform(0.98, 1.02)
    elif category == "EV Battery Parts (EV電池部品)":
        growth_rate = 1.0 + ((year - 2015) ** 1.8) * 0.1
        return base_revenue * growth_rate * np.random.uniform(0.9, 1.1)
    elif category == "Medical Catheters (医療用カテーテル)":
        growth_rate = 1.0 + (year - 2015) * 0.1
        return base_revenue * growth_rate * np.random.uniform(0.98, 1.02)
    return base_revenue


def _calculate_category_margin(
    category: str, base_margin: float, year: int, material_impact: float
) -> float:
    """カテゴリと年度に応じた利益率を計算"""
    if category in [
        "Standard Fasteners (汎用ファスナー)",
        "Precision Springs (精密ばね)",
    ]:
        return base_margin + material_impact + np.random.uniform(-0.01, 0.01)
    elif category == "Air Dampers (エアダンパー)":
        return base_margin + (material_impact * 0.3) + np.random.uniform(-0.01, 0.01)
    elif category == "EV Battery Parts (EV電池部品)":
        margin_improvement = (year - 2015) * 0.015
        return base_margin + margin_improvement + np.random.uniform(-0.02, 0.02)
    elif category == "Medical Catheters (医療用カテーテル)":
        return base_margin + np.random.uniform(-0.01, 0.01)
    return base_margin


def _calculate_volume(category: str, revenue: float) -> float:
    """カテゴリ別のボリューム計算（販売数量推定）"""
    divisors = {
        "Standard Fasteners (汎用ファスナー)": 100,
        "Precision Springs (精密ばね)": 100,
        "Air Dampers (エアダンパー)": 500,
        "EV Battery Parts (EV電池部品)": 1500,
        "Medical Catheters (医療用カテーテル)": 5000,
    }
    divisor = divisors.get(category, 1000)
    base_vol = revenue / divisor
    return base_vol * np.random.uniform(0.9, 1.1)


def ensure_historical_marginal_profit_data(output_path: str):
    """指定パスにPPMシミュレーションデータを生成"""
    if os.path.exists(output_path):
        return

    np.random.seed(42)  # 再現性担保
    categories = [
        "Standard Fasteners (汎用ファスナー)",
        "Precision Springs (精密ばね)",
        "Air Dampers (エアダンパー)",
        "EV Battery Parts (EV電池部品)",
        "Medical Catheters (医療用カテーテル)",
    ]
    years = range(2015, 2025)
    data = []
    base_metrics = _get_category_base_metrics()

    for year in years:
        factors = _get_year_factors(year)
        for category in categories:
            base_rev = base_metrics[category]["rev"]
            base_margin = base_metrics[category]["margin"]

            current_rev = _calculate_category_revenue(
                category, base_rev, year, factors["macro_revenue"]
            )
            current_margin = _calculate_category_margin(
                category, base_margin, year, factors["material_cost"]
            )
            current_margin = max(0.01, current_margin)
            current_vol = _calculate_volume(category, current_rev)
            current_mp = current_rev * current_margin

            data.append(
                {
                    "Year": year,
                    "Category": category,
                    "Total_Revenue": round(current_rev, 0),
                    "Total_Marginal_Profit": round(current_mp, 0),
                    "Avg_Margin": round(current_margin, 4),
                    "Total_Volume": round(current_vol, 0),
                }
            )

    df = pl.DataFrame(data)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.write_csv(output_path)


def load_marginal_profit_data(path: str):
    """CSV読み込み (polars DataFrameで返却)"""
    return pl.read_csv(path)
