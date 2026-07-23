"""
Unit tests for financial_metrics module

Tests ROIC, CCC calculations and safe value extraction functions.
"""

import numpy as np
import pandas as pd
import pytest
from consultant_toolkit.financial_metrics import (
    DAYS_PER_YEAR,
    DEFAULT_COGS_RATIO,
    DEFAULT_TAX_RATE,
    calculate_ccc,
    calculate_financial_metrics,
    calculate_roic,
    get_val_safe,
)


class TestGetValSafe:
    """Test suite for get_val_safe function"""

    def test_get_value_with_first_key(self):
        """Should return value when first key matches"""
        df = pd.DataFrame(
            {"2024": [100, 200]}, index=["Total Revenue", "Operating Income"]
        )
        result = get_val_safe(df, ["Total Revenue", "Revenue"], "2024")
        assert result == 100.0

    def test_get_value_with_second_key(self):
        """Should return value when second key matches"""
        df = pd.DataFrame({"2024": [100, 200]}, index=["Revenue", "Operating Income"])
        result = get_val_safe(df, ["Total Revenue", "Revenue"], "2024")
        assert result == 100.0

    def test_missing_key_returns_default(self):
        """Should return default when no keys match"""
        df = pd.DataFrame({"2024": [100]}, index=["Some Other Metric"])
        result = get_val_safe(df, ["Total Revenue", "Revenue"], "2024", default=999.0)
        assert result == 999.0

    def test_nan_value_tries_next_key(self):
        """Should try next key when value is NaN"""
        df = pd.DataFrame({"2024": [np.nan, 200]}, index=["Total Revenue", "Revenue"])
        result = get_val_safe(df, ["Total Revenue", "Revenue"], "2024")
        assert result == 200.0

    def test_missing_column_returns_default(self):
        """Should return default when column doesn't exist"""
        df = pd.DataFrame({"2024": [100]}, index=["Total Revenue"])
        result = get_val_safe(df, ["Total Revenue"], "2023", default=0.0)
        assert result == 0.0


class TestCalculateROIC:
    """Test suite for ROIC calculation"""

    def test_calculate_roic_basic(self):
        """Should calculate ROIC correctly with basic inputs"""
        result = calculate_roic(
            revenue=1000000,
            operating_income=200000,
            total_assets=5000000,
            current_liabilities=1000000,
            cash=500000,
            tax_rate=0.30,
        )

        # NOPAT = 200000 * (1 - 0.30) = 140000
        # Invested Capital = 5000000 - 1000000 - 500000 = 3500000
        # ROIC = 140000 / 3500000 = 0.04
        assert pytest.approx(result, rel=1e-4) == 0.04

    def test_calculate_roic_zero_invested_capital(self):
        """Should return 0 when invested capital is zero or negative"""
        result = calculate_roic(
            revenue=1000000,
            operating_income=200000,
            total_assets=1000000,
            current_liabilities=800000,
            cash=300000,  # IC = 1000000 - 800000 - 300000 = -100000
            tax_rate=0.30,
        )
        assert result == 0.0

    def test_calculate_roic_with_defaults(self):
        """Should use default tax rate when not provided"""
        result = calculate_roic(
            revenue=1000000,
            operating_income=200000,
            total_assets=5000000,
            current_liabilities=1000000,
            cash=500000,
            # tax_rate not provided, should use DEFAULT_TAX_RATE
        )
        expected_nopat = 200000 * (1 - DEFAULT_TAX_RATE)
        expected_ic = 5000000 - 1000000 - 500000
        expected_roic = expected_nopat / expected_ic
        assert pytest.approx(result, rel=1e-4) == expected_roic


class TestCalculateCCC:
    """Test suite for Cash Conversion Cycle calculation"""

    def test_calculate_ccc_basic(self):
        """Should calculate CCC correctly with basic inputs"""
        result = calculate_ccc(
            revenue=3650000,  # 365 days * 10000/day
            cogs=2190000,  # 60% of revenue
            inventory=60000,  # 6 days of COGS
            receivables=100000,  # 10 days of revenue
            payables=20000,  # 2 days of COGS
        )

        # DIO = (60000 / 2190000) * 365 ≈ 10 days
        # DSO = (100000 / 3650000) * 365 = 10 days
        # DPO = (20000 / 2190000) * 365 ≈ 3.33 days
        # CCC = 10 + 10 - 3.33 ≈ 16.67 days

        assert pytest.approx(result["dio"], rel=0.01) == 10.0
        assert pytest.approx(result["dso"], rel=0.01) == 10.0
        assert pytest.approx(result["dpo"], rel=0.01) == 3.33
        assert pytest.approx(result["ccc"], rel=0.01) == 16.67

    def test_calculate_ccc_zero_cogs(self):
        """Should return zeros when COGS is zero"""
        result = calculate_ccc(
            revenue=1000000, cogs=0, inventory=10000, receivables=50000, payables=5000
        )

        assert result["dio"] == 0.0
        assert result["dso"] > 0  # DSO should still be calculated
        assert result["dpo"] == 0.0
        assert result["ccc"] > 0

    def test_calculate_ccc_with_default_cogs_ratio(self):
        """Should estimate COGS when not provided"""
        result = calculate_ccc(
            revenue=1000000,
            cogs=None,  # Will be estimated as revenue * DEFAULT_COGS_RATIO
            inventory=30000,
            receivables=50000,
            payables=20000,
        )

        estimated_cogs = 1000000 * DEFAULT_COGS_RATIO
        expected_dio = (30000 / estimated_cogs) * DAYS_PER_YEAR

        assert pytest.approx(result["dio"], rel=0.01) == expected_dio


class TestCalculateFinancialMetrics:
    """Test suite for calculate_financial_metrics integration function"""

    def test_calculate_financial_metrics_full(self):
        """Should calculate all metrics from DataFrames correctly"""
        financials = pd.DataFrame(
            {
                "2024-12-31": [1000000, 200000, 600000],
            },
            index=["Total Revenue", "Operating Income", "Cost Of Revenue"],
        )

        balance_sheet = pd.DataFrame(
            {
                "2024-12-31": [5000000, 1000000, 500000, 100000, 50000, 20000],
            },
            index=[
                "Total Assets",
                "Current Liabilities",
                "Cash And Cash Equivalents",
                "Inventory",
                "Accounts Receivable",
                "Accounts Payable",
            ],
        )

        result = calculate_financial_metrics(financials, balance_sheet, "2024-12-31")

        # Verify all keys exist
        assert "revenue" in result
        assert "operating_income" in result
        assert "roic" in result
        assert "nopat" in result
        assert "invested_capital" in result
        assert "nopat_margin" in result
        assert "ic_turnover" in result

        # Verify values
        assert result["revenue"] == 1000000
        assert result["operating_income"] == 200000
        assert result["roic"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
