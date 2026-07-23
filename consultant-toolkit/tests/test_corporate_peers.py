"""render_corporate_peers のスモークテスト。"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import (
    _make_st_mock,
    mock_calculate_comprehensive_metrics,
    mock_calculate_financial_metrics,
    mock_get_val_safe,
    mock_load_financial_data,
)


def _mock_segment_analysis_module():
    """consultant_toolkit.segment_analysis モジュールのモック。"""
    import pandas as pd

    seg_mock = MagicMock()
    seg_mock.get_available_tickers.return_value = ["TEST"]
    seg_mock.get_segment_analysis.return_value = (
        pd.DataFrame(
            {
                "Segment": ["Product A", "Product B"],
                "Revenue": [600, 400],
                "Percentage": [60.0, 40.0],
            }
        ),
        pd.DataFrame(
            {
                "Region": ["Japan", "Overseas"],
                "Revenue": [700, 300],
                "Percentage": [70.0, 30.0],
            }
        ),
        "Mock Data",
    )
    seg_mock.add_segment_mapping = MagicMock()
    return seg_mock


@pytest.fixture(autouse=True)
def _patch_deps():
    st_mock = _make_st_mock()
    seg_mock = _mock_segment_analysis_module()

    with patch.dict(
        sys.modules,
        {
            "streamlit": st_mock,
            "consultant_toolkit.segment_analysis": seg_mock,
        },
    ):
        import importlib

        import consultant_toolkit.ui_components.corporate_peers as mod

        importlib.reload(mod)
        yield st_mock, mod


DYNAMIC_COMPANIES = {"テスト社": "TEST", "競合A": "COMP"}
DYNAMIC_COLORS = {"テスト社": "#1f77b4", "競合A": "#ff7f0e"}


class TestRenderCorporatePeers:
    """render_corporate_peers のテスト。"""

    def test_smoke_with_data(self, _patch_deps):
        """正常データでクラッシュしないこと。"""
        st_mock, mod = _patch_deps
        mod.render_corporate_peers(
            target_ticker="TEST",
            target_company_name="テスト社",
            DYNAMIC_COMPANIES=DYNAMIC_COMPANIES,
            DYNAMIC_COLORS=DYNAMIC_COLORS,
            load_financial_data=mock_load_financial_data,
            calculate_financial_metrics=mock_calculate_financial_metrics,
            get_val_safe=mock_get_val_safe,
            calculate_comprehensive_metrics=mock_calculate_comprehensive_metrics,
        )
        st_mock.header.assert_called()

    def test_smoke_empty_data(self, _patch_deps):
        """空データ時にクラッシュしないこと。"""
        st_mock, mod = _patch_deps

        def _empty(ticker):
            import pandas as pd

            return pd.DataFrame(), pd.DataFrame()

        mod.render_corporate_peers(
            target_ticker="EMPTY",
            target_company_name="空社",
            DYNAMIC_COMPANIES={"空社": "EMPTY"},
            DYNAMIC_COLORS={},
            load_financial_data=_empty,
            calculate_financial_metrics=mock_calculate_financial_metrics,
            get_val_safe=mock_get_val_safe,
            calculate_comprehensive_metrics=mock_calculate_comprehensive_metrics,
        )
