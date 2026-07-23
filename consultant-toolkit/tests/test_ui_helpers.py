"""Tests for ui_components.ui_helpers module."""

import pandas as pd
from consultant_toolkit.ui_components.ui_helpers import (
    BaseFinancials,
    color_by_sign,
    load_base_financials,
)

from tests.conftest import (
    _make_balance_sheet,
    _make_income_statement,
)
from tests.conftest import (
    mock_get_cashflow_data as _mock_get_cashflow,
)
from tests.conftest import (
    mock_get_val_safe as _mock_get_val_safe,
)
from tests.conftest import (
    mock_load_financial_data as _mock_load_financial_data,
)
from tests.conftest import (
    mock_load_financial_data_empty as _mock_load_empty,
)


def _mock_load_error(ticker):
    """接続エラーを投げるモックローダー。"""
    raise ConnectionError("Network error")


# ========================================
# BaseFinancials dataclass
# ========================================


class TestBaseFinancials:
    """BaseFinancials データクラスのテスト。"""

    def test_default_values(self):
        """デフォルト値で初期化可能。"""
        fin = BaseFinancials()
        assert fin.has_real_data is False
        assert fin.revenue == 100_000_000.0
        assert fin.oi_margin == 15.0
        assert fin.dio == 60.0

    def test_custom_values(self):
        """カスタム値で初期化可能。"""
        fin = BaseFinancials(has_real_data=True, revenue=500.0, ccc=42.0)
        assert fin.has_real_data is True
        assert fin.revenue == 500.0
        assert fin.ccc == 42.0

    def test_dataframe_fields_are_independent(self):
        """DataFrame フィールドが各インスタンスで独立。"""
        fin1 = BaseFinancials()
        fin2 = BaseFinancials()
        assert fin1.raw_income_statement is not fin2.raw_income_statement


# ========================================
# load_base_financials
# ========================================


class TestLoadBaseFinancials:
    """load_base_financials のテスト。"""

    def test_success_has_real_data(self):
        """正常取得時 has_real_data=True。"""
        fin = load_base_financials(
            "TEST", _mock_load_financial_data, _mock_get_val_safe
        )
        assert fin.has_real_data is True

    def test_revenue_extracted(self):
        """売上高が正しく取得される。"""
        fin = load_base_financials(
            "TEST", _mock_load_financial_data, _mock_get_val_safe
        )
        assert abs(fin.revenue - 1_000_000) < 0.01

    def test_margins_calculated(self):
        """マージン率が正しく計算される。"""
        fin = load_base_financials(
            "TEST", _mock_load_financial_data, _mock_get_val_safe
        )
        # COGS/Rev = 650000/1000000 = 65%
        assert abs(fin.cogs_ratio - 65.0) < 0.01
        # OpEx/Rev = 200000/1000000 = 20%
        assert abs(fin.opex_ratio - 20.0) < 0.01
        # OI/Rev = 150000/1000000 = 15%
        assert abs(fin.oi_margin - 15.0) < 0.01

    def test_roic_calculated(self):
        """ROIC が計算される（ゼロでない）。"""
        fin = load_base_financials(
            "TEST", _mock_load_financial_data, _mock_get_val_safe
        )
        assert fin.roic != 0.0
        # ROIC = NOPAT / IC * 100; IC = equity + debt = 700000
        assert fin.invested_capital == 700_000

    def test_ccc_components(self):
        """CCC 構成要素（DIO/DSO/DPO）が計算される。"""
        fin = load_base_financials(
            "TEST", _mock_load_financial_data, _mock_get_val_safe
        )
        # DIO = inventory / cogs * 365
        expected_dio = 100_000 / 650_000 * 365
        assert abs(fin.dio - expected_dio) < 0.1
        # DSO = receivables / revenue * 365
        expected_dso = 80_000 / 1_000_000 * 365
        assert abs(fin.dso - expected_dso) < 0.1
        # DPO = payables / cogs * 365
        expected_dpo = 60_000 / 650_000 * 365
        assert abs(fin.dpo - expected_dpo) < 0.1
        # CCC = DIO + DSO - DPO
        assert abs(fin.ccc - (fin.dio + fin.dso - fin.dpo)) < 0.01

    def test_cashflow_data(self):
        """キャッシュフローデータが取得される。"""
        fin = load_base_financials(
            "TEST",
            _mock_load_financial_data,
            _mock_get_val_safe,
            get_cashflow_data=_mock_get_cashflow,
        )
        assert fin.capex == 50_000  # abs(-50000)
        assert fin.ocf == 200_000
        assert fin.fcf == 150_000  # ocf - capex

    def test_no_cashflow_defaults_to_zero(self):
        """get_cashflow_data を渡さない場合 capex/ocf/fcf=0。"""
        fin = load_base_financials(
            "TEST", _mock_load_financial_data, _mock_get_val_safe
        )
        assert fin.capex == 0.0
        assert fin.ocf == 0.0
        assert fin.fcf == 0.0

    def test_empty_data_returns_defaults(self):
        """空データ時はデフォルト値 (has_real_data=False)。"""
        fin = load_base_financials("TEST", _mock_load_empty, _mock_get_val_safe)
        assert fin.has_real_data is False
        assert fin.revenue == 100_000_000.0
        assert fin.oi_margin == 15.0

    def test_connection_error_returns_defaults(self):
        """接続エラー時はデフォルト値。"""
        fin = load_base_financials("TEST", _mock_load_error, _mock_get_val_safe)
        assert fin.has_real_data is False

    def test_raw_dataframes_preserved(self):
        """元の DataFrame が raw_ フィールドに保持される。"""
        fin = load_base_financials(
            "TEST", _mock_load_financial_data, _mock_get_val_safe
        )
        assert not fin.raw_income_statement.empty
        assert not fin.raw_balance_sheet.empty

    def test_latest_year_set(self):
        """latest_year が設定される。"""
        fin = load_base_financials(
            "TEST", _mock_load_financial_data, _mock_get_val_safe
        )
        assert fin.latest_year == pd.Timestamp("2024-01-01")

    def test_zero_revenue_fallback_margins(self):
        """売上ゼロの場合マージンがデフォルト値にフォールバック。"""

        def _load_zero_revenue(ticker):
            return _make_income_statement(revenue=0, cogs=0, opex=0, oi=0), _make_balance_sheet()

        fin = load_base_financials("TEST", _load_zero_revenue, _mock_get_val_safe)
        assert fin.has_real_data is True
        assert fin.cogs_ratio == 65.0  # fallback
        assert fin.opex_ratio == 20.0
        assert fin.oi_margin == 15.0

    def test_cashflow_error_doesnt_crash(self):
        """キャッシュフロー取得エラーでも全体は成功する。"""

        def _bad_cashflow(ticker):
            raise ConnectionError("CF network error")

        fin = load_base_financials(
            "TEST",
            _mock_load_financial_data,
            _mock_get_val_safe,
            get_cashflow_data=_bad_cashflow,
        )
        assert fin.has_real_data is True
        assert fin.capex == 0.0
        assert fin.revenue == 1_000_000


# ========================================
# color_by_sign
# ========================================


class TestColorBySign:
    """color_by_sign のテスト。"""

    def test_positive_value(self):
        assert color_by_sign(10.0) == "#2ca02c"

    def test_negative_value(self):
        assert color_by_sign(-5.0) == "#d62728"

    def test_zero_is_positive(self):
        assert color_by_sign(0.0) == "#2ca02c"

    def test_custom_colors(self):
        assert color_by_sign(1.0, positive="green", negative="red") == "green"
        assert color_by_sign(-1.0, positive="green", negative="red") == "red"

    def test_works_with_pandas_apply(self):
        """pandas Series.apply で使える。"""
        s = pd.Series([10, -5, 0, 3, -1])
        result = s.apply(color_by_sign)
        assert result.tolist() == ["#2ca02c", "#d62728", "#2ca02c", "#2ca02c", "#d62728"]
