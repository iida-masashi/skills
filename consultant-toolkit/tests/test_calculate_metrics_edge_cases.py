"""
Edge case tests for financial metrics calculations

Tests boundary conditions, extreme values, and error scenarios.
"""

import numpy as np
import pandas as pd
import pytest
from consultant_toolkit.financial_metrics import (
    calculate_ccc,
    calculate_financial_metrics,
    calculate_roic,
    get_val_safe,
)


class TestROICEdgeCases:
    """Edge case tests for ROIC calculation"""

    def test_roic_with_zero_revenue(self):
        """Should handle zero revenue gracefully"""
        result = calculate_roic(
            revenue=0,
            operating_income=0,
            total_assets=1000000,
            current_liabilities=100000,
            cash=50000,
            tax_rate=0.30,
        )

        assert result == 0.0

    def test_roic_with_negative_operating_income(self):
        """Should handle negative operating income (loss)"""
        result = calculate_roic(
            revenue=1000000,
            operating_income=-200000,  # Operating loss
            total_assets=5000000,
            current_liabilities=1000000,
            cash=500000,
            tax_rate=0.30,
        )

        # NOPAT = -200000 * (1 - 0.30) = -140000
        # IC = 3500000
        # ROIC = -140000 / 3500000 = -0.04
        assert result < 0

    def test_roic_with_very_high_tax_rate(self):
        """Should handle tax rates close to 100%"""
        result = calculate_roic(
            revenue=1000000,
            operating_income=200000,
            total_assets=5000000,
            current_liabilities=1000000,
            cash=500000,
            tax_rate=0.99,  # 99% tax
        )

        # NOPAT should be very small
        assert 0 <= result < 0.01

    def test_roic_with_zero_tax_rate(self):
        """Should handle zero tax rate"""
        result = calculate_roic(
            revenue=1000000,
            operating_income=200000,
            total_assets=5000000,
            current_liabilities=1000000,
            cash=500000,
            tax_rate=0.0,
        )

        # NOPAT = 200000 * (1 - 0.0) = 200000
        # IC = 3500000
        # ROIC = 200000 / 3500000 ≈ 0.0571
        assert pytest.approx(result, rel=1e-3) == 0.0571

    def test_roic_with_very_large_numbers(self):
        """Should handle very large financial values"""
        result = calculate_roic(
            revenue=1e12,  # 1 trillion
            operating_income=1e11,  # 100 billion
            total_assets=5e12,
            current_liabilities=1e12,
            cash=5e11,
            tax_rate=0.30,
        )

        assert result > 0
        assert not np.isnan(result)
        assert not np.isinf(result)

    def test_roic_with_assets_less_than_liabilities(self):
        """Should return 0 when invested capital is negative (bankrupt scenario)"""
        result = calculate_roic(
            revenue=1000000,
            operating_income=200000,
            total_assets=1000000,
            current_liabilities=2000000,  # Liabilities > Assets
            cash=100000,
            tax_rate=0.30,
        )

        assert result == 0.0


class TestCCCEdgeCases:
    """Edge case tests for CCC calculation"""

    def test_ccc_with_zero_inventory(self):
        """Should handle zero inventory (service company)"""
        result = calculate_ccc(
            revenue=1000000,
            cogs=600000,
            inventory=0,  # No inventory
            receivables=50000,
            payables=20000,
        )

        assert result["dio"] == 0.0
        assert result["dso"] > 0
        assert result["dpo"] > 0
        assert result["ccc"] < result["dso"]  # CCC = DSO - DPO

    def test_ccc_with_zero_receivables(self):
        """Should handle zero receivables (cash-only business)"""
        result = calculate_ccc(
            revenue=1000000,
            cogs=600000,
            inventory=30000,
            receivables=0,  # All cash sales
            payables=20000,
        )

        assert result["dso"] == 0.0
        assert result["dio"] > 0
        assert result["dpo"] > 0

    def test_ccc_with_zero_payables(self):
        """Should handle zero payables (all suppliers paid immediately)"""
        result = calculate_ccc(
            revenue=1000000, cogs=600000, inventory=30000, receivables=50000, payables=0
        )

        assert result["dpo"] == 0.0
        assert result["ccc"] == result["dio"] + result["dso"]

    def test_ccc_with_very_high_inventory(self):
        """Should handle very high inventory days (slow-moving inventory)"""
        result = calculate_ccc(
            revenue=1000000,
            cogs=600000,
            inventory=600000,  # 1 year of COGS as inventory
            receivables=50000,
            payables=20000,
        )

        # DIO should be ~365 days
        assert result["dio"] > 300
        assert result["ccc"] > 300

    def test_ccc_with_negative_ccc(self):
        """Should handle negative CCC (get paid before paying suppliers)"""
        result = calculate_ccc(
            revenue=3650000,
            cogs=2190000,
            inventory=20000,  # Low inventory
            receivables=30000,  # Collect quickly
            payables=200000,  # Pay slowly
        )

        # CCC = DIO + DSO - DPO
        # If DPO is very high, CCC can be negative
        assert result["dpo"] > result["dio"] + result["dso"]
        assert result["ccc"] < 0

    def test_ccc_with_all_zeros(self):
        """Should handle all zero inputs gracefully"""
        result = calculate_ccc(
            revenue=0, cogs=0, inventory=0, receivables=0, payables=0
        )

        assert result["dio"] == 0.0
        assert result["dso"] == 0.0
        assert result["dpo"] == 0.0
        assert result["ccc"] == 0.0


class TestGetValSafeEdgeCases:
    """Edge case tests for get_val_safe function"""

    def test_get_val_safe_with_empty_dataframe(self):
        """Should return default when DataFrame is empty"""
        df = pd.DataFrame()

        result = get_val_safe(df, ["Revenue"], "2024", default=999.0)

        assert result == 999.0

    def test_get_val_safe_with_all_nan_values(self):
        """Should return default when all candidate keys have NaN"""
        df = pd.DataFrame(
            {"2024": [np.nan, np.nan, np.nan]},
            index=["Total Revenue", "Revenue", "Operating Revenue"],
        )

        result = get_val_safe(
            df, ["Total Revenue", "Revenue", "Operating Revenue"], "2024", default=0.0
        )

        assert result == 0.0

    def test_get_val_safe_with_infinity(self):
        """Should handle infinity values"""
        df = pd.DataFrame({"2024": [np.inf, 200.0]}, index=["Total Revenue", "Revenue"])

        result = get_val_safe(df, ["Total Revenue", "Revenue"], "2024")

        # Should return the inf value (first match)
        assert np.isinf(result)

    def test_get_val_safe_with_negative_infinity(self):
        """Should handle negative infinity values"""
        df = pd.DataFrame(
            {"2024": [-np.inf, 200.0]}, index=["Total Revenue", "Revenue"]
        )

        result = get_val_safe(df, ["Total Revenue", "Revenue"], "2024")

        # Should return the -inf value
        assert result == -np.inf

    def test_get_val_safe_with_mixed_types(self):
        """Should handle mixed data types"""
        df = pd.DataFrame(
            {"2024": [100, 200.5, 300]}, index=["IntValue", "FloatValue", "AnotherInt"]
        )

        result = get_val_safe(df, ["FloatValue"], "2024")

        assert result == 200.5
        assert isinstance(result, float)

    def test_get_val_safe_with_very_large_dataframe(self):
        """Should efficiently handle large DataFrames"""
        # Create large DataFrame with 10000 rows
        large_df = pd.DataFrame(
            {"2024": range(10000)}, index=[f"Row_{i}" for i in range(10000)]
        )

        result = get_val_safe(large_df, ["Row_5000"], "2024")

        assert result == 5000.0


class TestCalculateFinancialMetricsEdgeCases:
    """Edge case tests for calculate_financial_metrics"""

    def test_with_minimal_data(self):
        """Should handle DataFrames with minimal data"""
        financials = pd.DataFrame(
            {"2024-12-31": [1000000, 100000]},
            index=["Total Revenue", "Operating Income"],
        )

        balance_sheet = pd.DataFrame(
            {"2024-12-31": [500000, 50000, 10000]},
            index=["Total Assets", "Current Liabilities", "Cash And Cash Equivalents"],
        )

        result = calculate_financial_metrics(financials, balance_sheet, "2024-12-31")

        assert "revenue" in result
        assert "roic" in result
        assert result["revenue"] == 1000000

    def test_with_missing_optional_fields(self):
        """Should handle missing optional fields gracefully"""
        financials = pd.DataFrame({"2024-12-31": [1000000]}, index=["Total Revenue"])

        balance_sheet = pd.DataFrame({"2024-12-31": [500000]}, index=["Total Assets"])

        result = calculate_financial_metrics(financials, balance_sheet, "2024-12-31")

        # Should still calculate what it can
        assert "revenue" in result
        assert result["revenue"] == 1000000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
