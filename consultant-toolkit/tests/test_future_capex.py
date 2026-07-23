"""render_capex_analysis のスモークテスト。"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tests.conftest import (
    _PREV_YEAR,
    _YEAR,
    _make_st_mock,
    mock_get_val_safe,
    mock_load_financial_data,
)


def _mock_yfinance_module():
    """yfinance モジュールのモック。"""
    yf_mock = MagicMock()
    ticker_instance = MagicMock()

    # cash_flow DataFrame
    cf_data = {
        _YEAR: {
            "Capital Expenditure": -50_000,
            "Operating Cash Flow": 200_000,
            "Free Cash Flow": 150_000,
            "Depreciation And Amortization": 30_000,
        },
        _PREV_YEAR: {
            "Capital Expenditure": -45_000,
            "Operating Cash Flow": 180_000,
            "Free Cash Flow": 135_000,
            "Depreciation And Amortization": 28_000,
        },
    }
    ticker_instance.cash_flow = pd.DataFrame(cf_data)
    yf_mock.Ticker.return_value = ticker_instance
    return yf_mock


@pytest.fixture(autouse=True)
def _patch_deps():
    """streamlit と yfinance をモックに差し替える。"""
    st_mock = _make_st_mock()
    yf_mock = _mock_yfinance_module()

    with patch.dict(sys.modules, {"streamlit": st_mock, "yfinance": yf_mock}):
        import importlib

        import consultant_toolkit.ui_components.future_capex as mod

        importlib.reload(mod)
        yield st_mock, mod, yf_mock


class TestRenderCapexAnalysis:
    """render_capex_analysis のテスト。"""

    def test_smoke_with_data(self, _patch_deps):
        """正常データでクラッシュしないこと。"""
        st_mock, mod, _ = _patch_deps
        mod.render_capex_analysis(
            target_ticker="TEST",
            target_company_name="テスト社",
            load_financial_data=mock_load_financial_data,
            get_val_safe=mock_get_val_safe,
        )
        st_mock.header.assert_called()

    def test_smoke_connection_error(self, _patch_deps):
        """接続エラー時にクラッシュしないこと。"""
        st_mock, mod, yf_mock = _patch_deps
        yf_mock.Ticker.side_effect = ConnectionError("Network")
        mod.render_capex_analysis(
            target_ticker="ERR",
            target_company_name="エラー社",
            load_financial_data=mock_load_financial_data,
            get_val_safe=mock_get_val_safe,
        )
        # st.error が呼ばれるはず
        st_mock.error.assert_called()
