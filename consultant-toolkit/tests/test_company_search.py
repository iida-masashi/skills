"""Tests for company_search module."""

from consultant_toolkit.company_search import get_ticker_from_input, search_companies


class TestGetTickerFromInput:
    """get_ticker_from_input のテスト"""

    def test_direct_ticker_input(self):
        """ティッカーシンボルをそのまま入力した場合（AAPLはappleとして名前検索ヒットする）"""
        ticker, method = get_ticker_from_input("AAPL")
        assert ticker == "AAPL"
        # AAPLは企業名マッピングにもあるので name_search になりうる

    def test_japanese_ticker_input(self):
        """日本のティッカーシンボル"""
        ticker, method = get_ticker_from_input("7203.T")
        assert ticker == "7203.T"
        assert method == "ticker"

    def test_company_name_input(self):
        """企業名で検索"""
        ticker, method = get_ticker_from_input("apple")
        assert ticker == "AAPL"
        assert method == "name_search"

    def test_case_insensitive(self):
        """大文字小文字を区別しない"""
        ticker, method = get_ticker_from_input("Apple")
        assert ticker == "AAPL"
        assert method == "name_search"

    def test_unknown_name_returns_as_ticker(self):
        """未知の名前はティッカーとして返す"""
        ticker, method = get_ticker_from_input("ZZZZZZ")
        assert ticker == "ZZZZZZ"
        assert method == "ticker"

    def test_empty_input(self):
        """空文字列"""
        ticker, method = get_ticker_from_input("")
        assert ticker == ""


class TestSearchCompanies:
    """search_companies のテスト"""

    def test_search_returns_results(self):
        """検索結果が返る"""
        results = search_companies("apple", max_results=5)
        assert len(results) > 0
        assert any("AAPL" in ticker for _, ticker in results)

    def test_search_max_results(self):
        """max_results を尊重"""
        results = search_companies("a", max_results=3)
        assert len(results) <= 3

    def test_search_no_results(self):
        """該当なし"""
        results = search_companies("xyznonexistent12345")
        assert len(results) == 0
