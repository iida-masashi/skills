"""render_financial_trends のスモークテスト。"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from tests.conftest import (
    _make_st_mock,
    mock_ensure_historical_marginal_profit_data,
    mock_get_val_safe,
    mock_load_financial_data,
    mock_load_financial_data_empty,
    mock_load_marginal_profit_data,
)


@pytest.fixture(autouse=True)
def _patch_streamlit():
    """streamlit を全テストでモックに差し替える。"""
    st_mock = _make_st_mock()
    with patch.dict(sys.modules, {"streamlit": st_mock}):
        # モジュールを再インポートして st パッチを適用
        import importlib

        import consultant_toolkit.ui_components.detail_financial_trends as mod

        importlib.reload(mod)
        yield st_mock, mod


class TestRenderFinancialTrends:
    """render_financial_trends のテスト。"""

    def test_smoke_with_real_data(self, _patch_streamlit):
        """実データ有りパスでクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit
        mod.render_financial_trends(
            target_ticker="TEST",
            target_company_name="テスト株式会社",
            load_financial_data=mock_load_financial_data,
            get_val_safe=mock_get_val_safe,
            ensure_historical_marginal_profit_data=mock_ensure_historical_marginal_profit_data,
            load_marginal_profit_data=mock_load_marginal_profit_data,
        )
        # st.header が呼ばれた
        st_mock.header.assert_called()

    def test_smoke_empty_data_fallback(self, _patch_streamlit):
        """空データ時のフォールバックパスでクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit
        mod.render_financial_trends(
            target_ticker="EMPTY",
            target_company_name="空データ社",
            load_financial_data=mock_load_financial_data_empty,
            get_val_safe=mock_get_val_safe,
            ensure_historical_marginal_profit_data=mock_ensure_historical_marginal_profit_data,
            load_marginal_profit_data=mock_load_marginal_profit_data,
        )
        st_mock.header.assert_called()

    def test_smoke_connection_error(self, _patch_streamlit):
        """接続エラー時にクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit

        def _raise(ticker):
            raise ConnectionError("Network error")

        mod.render_financial_trends(
            target_ticker="ERR",
            target_company_name="エラー社",
            load_financial_data=_raise,
            get_val_safe=mock_get_val_safe,
            ensure_historical_marginal_profit_data=mock_ensure_historical_marginal_profit_data,
            load_marginal_profit_data=mock_load_marginal_profit_data,
        )
