"""render_roic_tree のスモークテスト。"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from tests.conftest import (
    _make_st_mock,
    mock_calculate_financial_metrics,
    mock_get_val_safe,
    mock_load_financial_data,
    mock_load_markdown_asset,
)


@pytest.fixture(autouse=True)
def _patch_streamlit():
    st_mock = _make_st_mock()
    with patch.dict(sys.modules, {"streamlit": st_mock}):
        import importlib

        import consultant_toolkit.ui_components.detail_roic_tree as mod

        importlib.reload(mod)
        yield st_mock, mod


DYNAMIC_COLORS = {"テスト社": "#1f77b4", "競合A": "#ff7f0e"}


class TestRenderRoicTree:
    """render_roic_tree のテスト。"""

    def test_smoke_with_data(self, _patch_streamlit):
        """正常データでクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit
        companies = {"テスト社": "TEST", "競合A": "COMP"}
        mod.render_roic_tree(
            target_ticker="TEST",
            DYNAMIC_COMPANIES=companies,
            DYNAMIC_COLORS=DYNAMIC_COLORS,
            load_financial_data=mock_load_financial_data,
            calculate_financial_metrics=mock_calculate_financial_metrics,
            get_val_safe=mock_get_val_safe,
            load_markdown_asset=mock_load_markdown_asset,
        )
        st_mock.header.assert_called()

    def test_smoke_empty_data(self, _patch_streamlit):
        """空データ時にクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit

        def _empty(ticker):
            import pandas as pd

            return pd.DataFrame(), pd.DataFrame()

        companies = {"空社": "EMPTY"}
        mod.render_roic_tree(
            target_ticker="EMPTY",
            DYNAMIC_COMPANIES=companies,
            DYNAMIC_COLORS={},
            load_financial_data=_empty,
            calculate_financial_metrics=mock_calculate_financial_metrics,
            get_val_safe=mock_get_val_safe,
            load_markdown_asset=mock_load_markdown_asset,
        )
