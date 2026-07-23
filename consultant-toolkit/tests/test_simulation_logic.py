"""Tests for simulation_logic module."""

from consultant_toolkit.simulation_logic import calculate_simulated_financials


class TestCalculateSimulatedFinancials:
    """calculate_simulated_financials のテスト"""

    def setup_method(self):
        """共通のベースデータ"""
        self.base = {
            "current_revenue": 100_000,
            "current_cogs_ratio": 65.0,
            "current_opex_ratio": 20.0,
            "current_dio": 60.0,
            "current_dso": 45.0,
            "current_dpo": 30.0,
            "current_capex": 10_000,
            "current_ocf": 20_000,
        }

    def test_no_change_returns_baseline(self):
        """変更なしの場合、基準値と同じ"""
        result = calculate_simulated_financials(**self.base)
        assert result["revenue"] == 100_000
        assert result["cogs"] == 65_000  # 65% of 100k
        assert result["opex"] == 20_000  # 20% of 100k
        assert result["operating_income"] == 15_000  # 100k - 65k - 20k
        assert result["ccc"] == 75.0  # 60 + 45 - 30

    def test_revenue_growth(self):
        """売上成長率の適用"""
        result = calculate_simulated_financials(
            **self.base, revenue_growth_pct=10.0
        )
        assert abs(result["revenue"] - 110_000) < 0.01

    def test_cogs_change(self):
        """原価率変更"""
        result = calculate_simulated_financials(
            **self.base, cogs_change_pp=-5.0
        )
        # COGS ratio: 65 - 5 = 60%
        assert result["cogs"] == 60_000

    def test_ccc_change(self):
        """CCC各要素の変更"""
        result = calculate_simulated_financials(
            **self.base, dio_change_days=-10, dso_change_days=-5, dpo_change_days=5
        )
        assert result["dio"] == 50.0
        assert result["dso"] == 40.0
        assert result["dpo"] == 35.0
        assert result["ccc"] == 55.0  # 50 + 40 - 35

    def test_negative_dio_clamped_to_zero(self):
        """DIOがマイナスにならない"""
        result = calculate_simulated_financials(
            **self.base, dio_change_days=-100
        )
        assert result["dio"] == 0.0

    def test_capex_change_affects_revenue(self):
        """CAPEX変更が売上に影響"""
        result = calculate_simulated_financials(
            **self.base, capex_change_pct=50.0, capex_efficiency=2.0
        )
        # CAPEX: 10k * 1.5 = 15k, delta = 5k, revenue addition = 5k * 2.0 = 10k
        assert result["capex"] == 15_000
        assert result["revenue"] == 110_000  # 100k + 10k

    def test_fcf_calculation(self):
        """FCF = OCF - CAPEX"""
        result = calculate_simulated_financials(**self.base)
        assert result["fcf"] == result["ocf"] - result["capex"]

    def test_zero_revenue(self):
        """売上ゼロの場合"""
        result = calculate_simulated_financials(
            current_revenue=0,
            current_cogs_ratio=65.0,
            current_opex_ratio=20.0,
            current_dio=0,
            current_dso=0,
            current_dpo=0,
            current_capex=0,
            current_ocf=0,
        )
        assert result["operating_margin"] == 0.0
