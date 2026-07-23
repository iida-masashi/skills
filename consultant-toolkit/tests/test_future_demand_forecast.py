"""render_demand_forecast のスモークテスト。"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from tests.conftest import (
    _make_st_mock,
    mock_get_val_safe,
    mock_load_financial_data,
    mock_load_financial_data_empty,
)


@pytest.fixture(autouse=True)
def _patch_streamlit():
    st_mock = _make_st_mock()
    with patch.dict(sys.modules, {"streamlit": st_mock}):
        import importlib

        import consultant_toolkit.ui_components.future_demand_forecast as mod

        importlib.reload(mod)
        yield st_mock, mod


class TestRenderDemandForecast:
    """render_demand_forecast のテスト。"""

    def test_smoke_with_data(self, _patch_streamlit):
        """正常データでクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit
        mod.render_demand_forecast(
            target_ticker="TEST",
            load_financial_data=mock_load_financial_data,
            get_val_safe=mock_get_val_safe,
        )
        st_mock.header.assert_called()

    def test_smoke_empty_data(self, _patch_streamlit):
        """空データ時にクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit
        mod.render_demand_forecast(
            target_ticker="EMPTY",
            load_financial_data=mock_load_financial_data_empty,
            get_val_safe=mock_get_val_safe,
        )
        st_mock.header.assert_called()
