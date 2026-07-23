"""
Unit tests for finance_data module

Tests yfinance data fetching and batch operations with mocking.
"""

from unittest.mock import Mock, patch

import pandas as pd
import pytest
from consultant_toolkit.finance_data import (
    FinancialData,
    fetch_financial_data,
    fetch_financial_data_batch,
    get_safe_value,
)


class TestGetSafeValue:
    """Test suite for get_safe_value function"""

    def test_get_value_with_first_key(self):
        """Should return value when first key exists"""
        df = pd.DataFrame(
            {"2024": [100.0, 200.0]}, index=["Total Revenue", "Operating Income"]
        )
        result = get_safe_value(df, ["Total Revenue", "Revenue"], "2024")
        assert result == 100.0

    def test_get_value_with_fallback_key(self):
        """Should return value from second key when first doesn't exist"""
        df = pd.DataFrame({"2024": [100.0]}, index=["Revenue"])
        result = get_safe_value(df, ["Total Revenue", "Revenue"], "2024")
        assert result == 100.0

    def test_missing_keys_returns_default(self):
        """Should return default value when no keys match"""
        df = pd.DataFrame({"2024": [100.0]}, index=["Other Metric"])
        result = get_safe_value(df, ["Total Revenue", "Revenue"], "2024", default=999.0)
        assert result == 999.0

    def test_nan_value_skips_to_next_key(self):
        """Should try next key when current value is NaN"""
        df = pd.DataFrame(
            {"2024": [float("nan"), 200.0]}, index=["Total Revenue", "Revenue"]
        )
        result = get_safe_value(df, ["Total Revenue", "Revenue"], "2024")
        assert result == 200.0


class TestFetchFinancialData:
    """Test suite for fetch_financial_data with mocking"""

    @patch("consultant_toolkit.finance_data.yf.Ticker")
    def test_fetch_successful(self, mock_ticker_class):
        """Should return FinancialData when fetch is successful"""
        # Setup mock
        mock_ticker = Mock()
        mock_ticker.info = {"longName": "Test Company"}
        mock_ticker.financials = pd.DataFrame({"2024": [1000]}, index=["Total Revenue"])
        mock_ticker.balance_sheet = pd.DataFrame(
            {"2024": [5000]}, index=["Total Assets"]
        )
        mock_ticker_class.return_value = mock_ticker

        # Execute
        result = fetch_financial_data("TEST.T")

        # Verify
        assert result is not None
        assert isinstance(result, FinancialData)
        assert result.ticker_symbol == "TEST.T"
        assert result.info["longName"] == "Test Company"
        assert not result.financials.empty
        assert not result.balance_sheet.empty

    @patch("consultant_toolkit.finance_data.yf.Ticker")
    def test_fetch_with_empty_dataframes(self, mock_ticker_class):
        """Should return None when DataFrames are empty"""
        mock_ticker = Mock()
        mock_ticker.info = {}
        mock_ticker.financials = pd.DataFrame()  # Empty
        mock_ticker.balance_sheet = pd.DataFrame()  # Empty
        mock_ticker_class.return_value = mock_ticker

        result = fetch_financial_data("INVALID.T")

        assert result is None

    @patch("consultant_toolkit.finance_data.yf.Ticker")
    def test_fetch_with_cash_flow(self, mock_ticker_class):
        """Should include cash flow when requested"""
        mock_ticker = Mock()
        mock_ticker.info = {}
        mock_ticker.financials = pd.DataFrame({"2024": [1000]}, index=["Revenue"])
        mock_ticker.balance_sheet = pd.DataFrame({"2024": [5000]}, index=["Assets"])
        mock_ticker.cash_flow = pd.DataFrame({"2024": [100]}, index=["Operating CF"])
        mock_ticker_class.return_value = mock_ticker

        result = fetch_financial_data("TEST.T", include_cash_flow=True)

        assert result is not None
        assert result.cash_flow is not None
        assert not result.cash_flow.empty

    @patch("consultant_toolkit.finance_data.yf.Ticker")
    def test_fetch_with_history(self, mock_ticker_class):
        """Should include price history when period is specified"""
        mock_ticker = Mock()
        mock_ticker.info = {}
        mock_ticker.financials = pd.DataFrame({"2024": [1000]}, index=["Revenue"])
        mock_ticker.balance_sheet = pd.DataFrame({"2024": [5000]}, index=["Assets"])
        mock_ticker.history.return_value = pd.DataFrame({"Close": [100, 101, 102]})
        mock_ticker_class.return_value = mock_ticker

        result = fetch_financial_data("TEST.T", history_period="1y")

        assert result is not None
        assert result.history is not None
        mock_ticker.history.assert_called_once_with(period="1y")

    @patch("consultant_toolkit.finance_data.yf.Ticker")
    def test_fetch_handles_key_error(self, mock_ticker_class):
        """Should return None when KeyError occurs"""
        mock_ticker = Mock()
        mock_ticker.info = {}
        mock_ticker.financials = pd.DataFrame({"2024": [1000]}, index=["Revenue"])
        # Simulate KeyError
        mock_ticker.balance_sheet = pd.DataFrame()
        mock_ticker_class.return_value = mock_ticker

        result = fetch_financial_data("TEST.T")

        assert result is None


class TestFetchFinancialDataBatch:
    """Test suite for batch data fetching"""

    @patch("consultant_toolkit.finance_data.fetch_financial_data")
    def test_batch_fetch_successful(self, mock_fetch):
        """Should fetch multiple tickers in parallel"""

        # Setup mock to return different data for each ticker
        def mock_fetch_side_effect(ticker, *args, **kwargs):
            if ticker == "TEST1.T":
                return FinancialData(
                    ticker_symbol="TEST1.T",
                    info={"longName": "Test 1"},
                    financials=pd.DataFrame(),
                    balance_sheet=pd.DataFrame(),
                )
            elif ticker == "TEST2.T":
                return FinancialData(
                    ticker_symbol="TEST2.T",
                    info={"longName": "Test 2"},
                    financials=pd.DataFrame(),
                    balance_sheet=pd.DataFrame(),
                )
            return None

        mock_fetch.side_effect = mock_fetch_side_effect

        # Execute
        tickers = ["TEST1.T", "TEST2.T"]
        results = fetch_financial_data_batch(tickers, max_workers=2)

        # Verify
        assert len(results) == 2
        assert "TEST1.T" in results
        assert "TEST2.T" in results
        assert results["TEST1.T"] is not None
        assert results["TEST2.T"] is not None

    @patch("consultant_toolkit.finance_data.fetch_financial_data")
    def test_batch_fetch_handles_failures(self, mock_fetch):
        """Should handle individual fetch failures gracefully"""

        def mock_fetch_side_effect(ticker, *args, **kwargs):
            if ticker == "VALID.T":
                return FinancialData(
                    ticker_symbol="VALID.T",
                    info={},
                    financials=pd.DataFrame({"2024": [1]}, index=["Revenue"]),
                    balance_sheet=pd.DataFrame({"2024": [1]}, index=["Assets"]),
                )
            else:
                raise ValueError("Invalid ticker")

        mock_fetch.side_effect = mock_fetch_side_effect

        # Execute
        tickers = ["VALID.T", "INVALID.T"]
        results = fetch_financial_data_batch(tickers)

        # Verify
        assert len(results) == 2
        assert results["VALID.T"] is not None
        assert results["INVALID.T"] is None  # Failed fetch returns None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
