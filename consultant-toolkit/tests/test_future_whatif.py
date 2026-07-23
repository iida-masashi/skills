"""render_whatif_simulator のスモークテスト。"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from tests.conftest import (
    _make_st_mock,
    mock_get_cashflow_data,
    mock_get_val_safe,
    mock_load_financial_data,
    mock_load_financial_data_empty,
)


@pytest.fixture(autouse=True)
def _patch_streamlit():
    st_mock = _make_st_mock()
    with patch.dict(sys.modules, {"streamlit": st_mock}):
        import importlib

        import consultant_toolkit.ui_components.future_whatif as mod

        importlib.reload(mod)
        yield st_mock, mod


class TestRenderWhatifSimulator:
    """render_whatif_simulator のテスト。"""

    def test_smoke_with_data(self, _patch_streamlit):
        """正常データでクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit
        mod.render_whatif_simulator(
            target_ticker="TEST",
            target_company_name="テスト社",
            load_financial_data=mock_load_financial_data,
            get_cashflow_data=mock_get_cashflow_data,
            get_val_safe=mock_get_val_safe,
        )
        st_mock.header.assert_called()

    def test_smoke_empty_data(self, _patch_streamlit):
        """空データ時にデフォルト値でクラッシュしないこと。"""
        st_mock, mod = _patch_streamlit
        mod.render_whatif_simulator(
            target_ticker="EMPTY",
            target_company_name="空データ社",
            load_financial_data=mock_load_financial_data_empty,
            get_cashflow_data=mock_get_cashflow_data,
            get_val_safe=mock_get_val_safe,
        )

    def test_button_not_clicked_no_export(self, _patch_streamlit):
        """ボタン未クリック時にエクスポート処理が走らないこと。"""
        st_mock, mod = _patch_streamlit
        st_mock.button.return_value = False
        mod.render_whatif_simulator(
            target_ticker="TEST",
            target_company_name="テスト社",
            load_financial_data=mock_load_financial_data,
            get_cashflow_data=mock_get_cashflow_data,
            get_val_safe=mock_get_val_safe,
        )
        # download_button はボタン未押下なので呼ばれない
        st_mock.download_button.assert_not_called()
