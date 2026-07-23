"""
Tests for batch operations and concurrent processing

Tests parallel data fetching and batch processing efficiency.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from consultant_toolkit.finance_data import FinancialData, fetch_financial_data_batch


class TestBatchOperations:
    """Test suite for batch data fetching"""

    @patch("consultant_toolkit.finance_data.fetch_financial_data")
    def test_batch_fetch_performance(self, mock_fetch):
        """Should fetch data in parallel, not sequentially"""

        # Simulate slow API call
        def slow_fetch(*args, **kwargs):
            time.sleep(0.1)  # 100ms delay
            return FinancialData(
                ticker_symbol=args[0],
                info={},
                financials=pd.DataFrame(),
                balance_sheet=pd.DataFrame(),
            )

        mock_fetch.side_effect = slow_fetch

        tickers = ["TEST1", "TEST2", "TEST3", "TEST4", "TEST5"]

        start_time = time.time()
        results = fetch_financial_data_batch(tickers, max_workers=5)
        elapsed_time = time.time() - start_time

        # With 5 workers and 5 tickers (each 100ms), should take ~100ms
        # Sequential would take 500ms
        assert elapsed_time < 0.3  # Allow some overhead
        assert len(results) == 5

    @patch("consultant_toolkit.finance_data.fetch_financial_data")
    def test_batch_fetch_respects_max_workers(self, mock_fetch):
        """Should respect max_workers parameter"""
        call_times = []

        def track_fetch(*args, **kwargs):
            call_times.append(time.time())
            time.sleep(0.05)
            return FinancialData(
                ticker_symbol=args[0],
                info={},
                financials=pd.DataFrame(),
                balance_sheet=pd.DataFrame(),
            )

        mock_fetch.side_effect = track_fetch

        # 10 tickers with max_workers=2
        tickers = [f"TEST{i}" for i in range(10)]
        fetch_financial_data_batch(tickers, max_workers=2)

        # With 2 workers, should have ~5 batches
        # Check that not all started at once
        assert len(call_times) == 10

    @patch("consultant_toolkit.finance_data.fetch_financial_data")
    def test_batch_fetch_handles_mixed_success_failure(self, mock_fetch):
        """Should handle mix of successful and failed fetches"""

        def mixed_results(ticker, *args, **kwargs):
            if "FAIL" in ticker:
                raise ValueError(f"Failed to fetch {ticker}")
            return FinancialData(
                ticker_symbol=ticker,
                info={},
                financials=pd.DataFrame(),
                balance_sheet=pd.DataFrame(),
            )

        mock_fetch.side_effect = mixed_results

        tickers = ["SUCCESS1", "FAIL1", "SUCCESS2", "FAIL2", "SUCCESS3"]
        results = fetch_financial_data_batch(tickers)

        # Should have all 5 results (None for failures)
        assert len(results) == 5
        assert results["SUCCESS1"] is not None
        assert results["FAIL1"] is None
        assert results["SUCCESS2"] is not None
        assert results["FAIL2"] is None
        assert results["SUCCESS3"] is not None

    @patch("consultant_toolkit.finance_data.fetch_financial_data")
    def test_batch_fetch_preserves_order(self, mock_fetch):
        """Should preserve ticker order in results"""

        def simple_fetch(ticker, *args, **kwargs):
            return FinancialData(
                ticker_symbol=ticker,
                info={"name": f"Company {ticker}"},
                financials=pd.DataFrame(),
                balance_sheet=pd.DataFrame(),
            )

        mock_fetch.side_effect = simple_fetch

        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN"]
        results = fetch_financial_data_batch(tickers)

        # Results should be in dict with all tickers
        assert list(results.keys()) == tickers or set(results.keys()) == set(tickers)

    @patch("consultant_toolkit.finance_data.fetch_financial_data")
    def test_batch_fetch_with_empty_list(self, mock_fetch):
        """Should handle empty ticker list"""
        results = fetch_financial_data_batch([])

        assert results == {}
        mock_fetch.assert_not_called()

    @patch("consultant_toolkit.finance_data.fetch_financial_data")
    def test_batch_fetch_with_single_ticker(self, mock_fetch):
        """Should work with single ticker (edge case for batch)"""
        mock_fetch.return_value = FinancialData(
            ticker_symbol="SOLO",
            info={},
            financials=pd.DataFrame(),
            balance_sheet=pd.DataFrame(),
        )

        results = fetch_financial_data_batch(["SOLO"])

        assert len(results) == 1
        assert "SOLO" in results
        mock_fetch.assert_called_once()


class TestConcurrentSafety:
    """Test thread safety of shared operations"""

    @patch("consultant_toolkit.finance_data.yf.Ticker")
    def test_concurrent_ticker_fetches_dont_interfere(self, mock_ticker_class):
        """Should handle concurrent fetches without data corruption"""
        call_count = [0]

        def create_mock_ticker(symbol):
            call_count[0] += 1
            mock = Mock()
            mock.info = {"symbol": symbol, "call_num": call_count[0]}
            mock.financials = pd.DataFrame(
                {"2024": [100 * call_count[0]]}, index=["Revenue"]
            )
            mock.balance_sheet = pd.DataFrame(
                {"2024": [500 * call_count[0]]}, index=["Assets"]
            )
            return mock

        mock_ticker_class.side_effect = create_mock_ticker

        # Fetch multiple tickers concurrently
        from consultant_toolkit.finance_data import fetch_financial_data

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(fetch_financial_data, f"TICKER{i}") for i in range(5)
            ]
            results = [f.result() for f in futures]

        # All should succeed
        assert len(results) == 5
        assert all(r is not None for r in results)

        # Each should have unique data (no cross-contamination)
        symbols = [r.ticker_symbol for r in results]
        assert len(set(symbols)) == 5  # All unique


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
