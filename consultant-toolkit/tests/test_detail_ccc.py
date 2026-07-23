"""render_ccc_analysis のスモークテスト。"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from tests.conftest import (
    _make_st_mock,
    mock_calculate_ccc_metrics,
    mock_load_financial_data,
    mock_load_markdown_asset,
)


@pytest.fixture(autouse=True)
def _patch_streamlit():
    st_mock = _make_st_mock()
    with patch.dict(sys.modules, {"streamlit": st_mock}):
        import importlib

        import consultant_toolkit.ui_components.detail_ccc as mod

        importlib.reload(mod)
        yield st_mock, mod


class TestRenderCccAnalysis:
    """render_ccc_analysis のテスト。"""

    def test_smoke_with_data(self, _patch_streamlit):
        """正常データでクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit
        companies = {"テスト社": "TEST"}
        mod.render_ccc_analysis(
            target_company_name="テスト社",
            DYNAMIC_COMPANIES=companies,
            load_financial_data=mock_load_financial_data,
            calculate_ccc_metrics=mock_calculate_ccc_metrics,
            load_markdown_asset=mock_load_markdown_asset,
        )
        st_mock.header.assert_called()

    def test_smoke_empty_data(self, _patch_streamlit):
        """空データ時にクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit

        def _empty_loader(ticker):
            import pandas as pd

            return pd.DataFrame(), pd.DataFrame()

        companies = {"空社": "EMPTY"}
        mod.render_ccc_analysis(
            target_company_name="空社",
            DYNAMIC_COMPANIES=companies,
            load_financial_data=_empty_loader,
            calculate_ccc_metrics=mock_calculate_ccc_metrics,
            load_markdown_asset=mock_load_markdown_asset,
        )

    def test_smoke_connection_error(self, _patch_streamlit):
        """接続エラー時にクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit

        def _raise(ticker):
            raise ConnectionError("Network error")

        companies = {"エラー社": "ERR"}
        mod.render_ccc_analysis(
            target_company_name="エラー社",
            DYNAMIC_COMPANIES=companies,
            load_financial_data=_raise,
            calculate_ccc_metrics=mock_calculate_ccc_metrics,
            load_markdown_asset=mock_load_markdown_asset,
        )
