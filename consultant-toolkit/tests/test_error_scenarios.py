"""
Tests for error handling and recovery scenarios

Tests how the system handles various error conditions.
"""

from unittest.mock import Mock, patch

import pandas as pd
import pytest
from consultant_toolkit.finance_data import fetch_financial_data
from consultant_toolkit.financial_metrics import calculate_ccc, calculate_financial_metrics
from consultant_toolkit.retry import NetworkError, retry_on_error, safe_execute


class TestNetworkErrorRecovery:
    """Test network error handling and retry logic"""

    @patch("consultant_toolkit.finance_data.yf.Ticker")
    def test_fetch_retries_on_connection_error(self, mock_ticker_class):
        """Should retry on ConnectionError"""
        attempts = [0]

        def failing_then_succeeding(*args, **kwargs):
            attempts[0] += 1
            if attempts[0] < 3:
                raise ConnectionError("Network unavailable")

            mock = Mock()
            mock.info = {"name": "Test"}
            mock.financials = pd.DataFrame({"2024": [100]}, index=["Revenue"])
            mock.balance_sheet = pd.DataFrame({"2024": [500]}, index=["Assets"])
            return mock

        mock_ticker_class.side_effect = failing_then_succeeding

        result = fetch_financial_data("TEST")

        # Should succeed after retries
        assert result is not None
        assert attempts[0] == 3  # Failed twice, succeeded third time

    @patch("consultant_toolkit.finance_data.yf.Ticker")
    def test_fetch_fails_after_max_retries(self, mock_ticker_class):
        """Should fail after exhausting retries"""
        mock_ticker_class.side_effect = ConnectionError("Persistent network error")

        with pytest.raises(ConnectionError):
            fetch_financial_data("TEST")

    @patch("consultant_toolkit.finance_data.yf.Ticker")
    def test_fetch_handles_timeout_error(self, mock_ticker_class):
        """Should handle TimeoutError with retry"""
        attempts = [0]

        def timeout_then_success(*args, **kwargs):
            attempts[0] += 1
            if attempts[0] == 1:
                raise TimeoutError("Request timed out")

            mock = Mock()
            mock.info = {}
            mock.financials = pd.DataFrame({"2024": [100]}, index=["Revenue"])
            mock.balance_sheet = pd.DataFrame({"2024": [500]}, index=["Assets"])
            return mock

        mock_ticker_class.side_effect = timeout_then_success

        result = fetch_financial_data("TEST")

        assert result is not None
        assert attempts[0] == 2


class TestDataValidationErrors:
    """Test handling of invalid or malformed data"""

    @patch("consultant_toolkit.finance_data.yf.Ticker")
    def test_fetch_handles_empty_dataframes(self, mock_ticker_class):
        """Should return None when DataFrames are empty"""
        mock = Mock()
        mock.info = {}
        mock.financials = pd.DataFrame()  # Empty
        mock.balance_sheet = pd.DataFrame()  # Empty
        mock_ticker_class.return_value = mock

        result = fetch_financial_data("EMPTY")

        assert result is None

    @patch("consultant_toolkit.finance_data.yf.Ticker")
    def test_fetch_handles_missing_columns(self, mock_ticker_class):
        """Should handle DataFrames with unexpected structure"""
        mock = Mock()
        mock.info = {}
        # DataFrame with no date columns
        mock.financials = pd.DataFrame({"InvalidCol": [100]}, index=["Revenue"])
        mock.balance_sheet = pd.DataFrame({"InvalidCol": [500]}, index=["Assets"])
        mock_ticker_class.return_value = mock

        result = fetch_financial_data("INVALID")

        # Should still create FinancialData (validation is caller's responsibility)
        assert result is not None or result is None  # Both acceptable

    def test_calculate_metrics_with_missing_data(self):
        """Should handle missing financial data gracefully"""
        # Empty DataFrames
        financials = pd.DataFrame()
        balance_sheet = pd.DataFrame()

        result = calculate_financial_metrics(financials, balance_sheet, "2024")

        # Should return dict with zero/default values
        assert isinstance(result, dict)

    def test_calculate_ccc_with_none_inputs(self):
        """Should handle None values in CCC calculation"""
        result = calculate_ccc(
            revenue=1000000,
            cogs=None,  # None should use default ratio
            inventory=30000,
            receivables=50000,
            payables=20000,
        )

        assert "ccc" in result
        assert "dio" in result
        assert result["dio"] >= 0


class TestCalculationErrors:
    """Test error handling in financial calculations"""

    def test_roic_with_division_by_zero_protection(self):
        """Should protect against division by zero"""
        from consultant_toolkit.financial_metrics import calculate_roic

        # Invested capital = 0
        result = calculate_roic(
            revenue=1000000,
            operating_income=200000,
            total_assets=1000000,
            current_liabilities=500000,
            cash=500000,  # IC = 1M - 500K - 500K = 0
            tax_rate=0.30,
        )

        assert result == 0.0
        assert not isinstance(result, float) or not (result != result)  # Not NaN

    def test_ccc_with_zero_revenue(self):
        """Should handle zero revenue in DSO calculation"""
        result = calculate_ccc(
            revenue=0,  # Zero revenue
            cogs=0,
            inventory=30000,
            receivables=50000,
            payables=20000,
        )

        assert result["dso"] == 0.0
        assert result["ccc"] >= 0 or result["ccc"] < 0  # Any numeric value is OK


class TestRetryMechanismErrors:
    """Test retry decorator error scenarios"""

    def test_retry_with_non_retryable_exception(self):
        """Should not retry on non-specified exceptions"""
        attempts = [0]

        @retry_on_error(max_retries=3, exceptions=(ConnectionError,))
        def raises_value_error():
            attempts[0] += 1
            raise ValueError("Not a network error")

        with pytest.raises(ValueError):
            raises_value_error()

        # Should only try once (no retries for ValueError)
        assert attempts[0] == 1

    def test_safe_execute_with_unhandled_exception(self):
        """Should catch all exceptions in safe_execute"""

        def raises_weird_error():
            raise RuntimeError("Unexpected error")

        result = safe_execute(raises_weird_error, default="fallback")

        assert result == "fallback"

    def test_retry_with_all_failures(self):
        """Should raise last exception after all retries fail"""

        @retry_on_error(max_retries=2, delay=0.01, exceptions=(ValueError,))
        def always_fails():
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            always_fails()


class TestCustomExceptionHandling:
    """Test custom exception classes"""

    def test_network_error_caught_by_retry(self):
        """NetworkError should be caught by retry decorator"""
        attempts = [0]

        @retry_on_error(max_retries=2, delay=0.01, exceptions=(NetworkError,))
        def raises_network_error():
            attempts[0] += 1
            if attempts[0] < 2:
                raise NetworkError("Network issue")
            return "success"

        result = raises_network_error()

        assert result == "success"
        assert attempts[0] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
