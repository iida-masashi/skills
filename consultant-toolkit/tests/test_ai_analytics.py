"""Tests for ai_analytics module."""

import pandas as pd
from consultant_toolkit.ai_analytics import (
    calculate_growth_rates,
    generate_insights,
)


class TestCalculateGrowthRates:
    """calculate_growth_rates のテスト"""

    def test_basic_growth(self):
        """基本的な成長率計算"""
        df = pd.DataFrame({
            "Year": [2020, 2021, 2022],
            "Revenue": [100, 110, 121],
        })
        result = calculate_growth_rates(df, "Revenue")
        assert "Revenue_YoY_Growth" in result.columns
        # 2021: (110/100 - 1) * 100 = 10%
        assert abs(result["Revenue_YoY_Growth"].iloc[1] - 10.0) < 0.01

    def test_cagr_calculation(self):
        """CAGR計算"""
        df = pd.DataFrame({
            "Year": [2020, 2021, 2022],
            "Revenue": [100, 110, 121],
        })
        result = calculate_growth_rates(df, "Revenue")
        assert "Revenue_CAGR" in result.columns
        # CAGR = (121/100)^(1/2) - 1 = 10%
        assert abs(result["Revenue_CAGR"].iloc[0] - 10.0) < 0.01

    def test_single_row(self):
        """1行だけのデータ"""
        df = pd.DataFrame({"Year": [2020], "Revenue": [100]})
        result = calculate_growth_rates(df, "Revenue")
        assert "Revenue_YoY_Growth" in result.columns


class TestGenerateInsights:
    """generate_insights のテスト"""

    def test_high_roic(self):
        """ROICが十分高い場合"""
        df = pd.DataFrame({
            "Company": ["A", "B"],
            "ROIC": [0.15, 0.20],
        })
        insights = generate_insights(df)
        assert len(insights) > 0

    def test_low_roic_warning(self):
        """ROICが低い場合の警告"""
        df = pd.DataFrame({
            "Company": ["A"],
            "ROIC": [0.03],
        })
        insights = generate_insights(df)
        assert any("5%" in i for i in insights)

    def test_high_ccc_warning(self):
        """CCCが長い場合の警告"""
        df = pd.DataFrame({
            "Company": ["A"],
            "CCC": [120],
        })
        insights = generate_insights(df)
        assert any("90" in i for i in insights)

    def test_empty_dataframe(self):
        """空のDataFrame"""
        df = pd.DataFrame()
        insights = generate_insights(df)
        assert insights == []
