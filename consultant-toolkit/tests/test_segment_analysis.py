"""Tests for segment_analysis module."""

from consultant_toolkit.segment_analysis import (
    add_segment_mapping,
    calculate_segment_revenue,
    get_available_tickers,
    get_geographic_revenue,
    get_segment_data_manual,
)


class TestGetSegmentDataManual:
    """手動セグメントマッピングのテスト"""

    def test_known_ticker(self):
        """既知のティッカー"""
        data = get_segment_data_manual("AAPL")
        assert data is not None
        assert "segments" in data
        assert "iPhone" in data["segments"]

    def test_case_insensitive(self):
        """大文字小文字を区別しない"""
        data = get_segment_data_manual("aapl")
        assert data is not None

    def test_unknown_ticker(self):
        """未知のティッカー"""
        data = get_segment_data_manual("ZZZZ")
        assert data is None

    def test_japanese_ticker(self):
        """日本企業のティッカー"""
        data = get_segment_data_manual("7203.T")
        assert data is not None
        assert data["company_name"] == "トヨタ自動車株式会社"


class TestCalculateSegmentRevenue:
    """セグメント別収益計算のテスト"""

    def test_basic_calculation(self):
        """基本的な計算"""
        df = calculate_segment_revenue("AAPL", 1_000_000)
        assert df is not None
        assert len(df) > 0
        assert "Revenue" in df.columns
        # 合計が元の値に近い
        assert abs(df["Revenue"].sum() - 1_000_000) < 1

    def test_unknown_ticker_returns_none(self):
        """未知のティッカーではNone"""
        df = calculate_segment_revenue("ZZZZ", 1_000_000)
        assert df is None

    def test_sorted_by_revenue(self):
        """収益の降順でソートされている"""
        df = calculate_segment_revenue("AAPL", 1_000_000)
        assert df is not None
        revenues = df["Revenue"].tolist()
        assert revenues == sorted(revenues, reverse=True)


class TestGetGeographicRevenue:
    """地域別収益のテスト"""

    def test_known_ticker(self):
        """既知のティッカー"""
        df = get_geographic_revenue("AAPL", 1_000_000)
        assert df is not None
        assert "Region" in df.columns

    def test_unknown_ticker(self):
        """未知のティッカー"""
        df = get_geographic_revenue("ZZZZ", 1_000_000)
        assert df is None


class TestAddSegmentMapping:
    """カスタムセグメント追加のテスト"""

    def test_add_custom_mapping(self):
        """カスタムマッピングの追加"""
        segments = {
            "Product A": {"percentage": 0.6, "description": "Main"},
            "Product B": {"percentage": 0.4, "description": "Sub"},
        }
        add_segment_mapping("TEST.X", "Test Corp", segments, 2024)
        data = get_segment_data_manual("TEST.X")
        assert data is not None
        assert data["company_name"] == "Test Corp"


class TestGetAvailableTickers:
    """利用可能ティッカーリストのテスト"""

    def test_returns_list(self):
        """リストが返る"""
        tickers = get_available_tickers()
        assert isinstance(tickers, list)
        assert "AAPL" in tickers
