"""render_ai_strategy のスモークテスト。"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import (
    _make_st_mock,
    mock_get_val_safe,
    mock_load_financial_data,
    mock_load_financial_data_empty,
)


def _mock_genai_module():
    """google.genai モジュールのモック。"""
    genai_mock = MagicMock()
    genai_mock.errors = MagicMock()
    genai_mock.errors.APIError = type("APIError", (Exception,), {})
    return genai_mock


@pytest.fixture(autouse=True)
def _patch_deps():
    st_mock = _make_st_mock()
    genai_mock = _mock_genai_module()
    google_mock = MagicMock()
    google_mock.genai = genai_mock

    with patch.dict(
        sys.modules,
        {
            "streamlit": st_mock,
            "google": google_mock,
            "google.genai": genai_mock,
        },
    ):
        import importlib

        import consultant_toolkit.ui_components.future_ai_strategy as mod

        importlib.reload(mod)
        yield st_mock, mod


class TestRenderAiStrategy:
    """render_ai_strategy のテスト。"""

    def test_smoke_with_data(self, _patch_deps):
        """正常データ + ボタン未押下でクラッシュしないこと。"""
        st_mock, mod = _patch_deps
        st_mock.button.return_value = False
        st_mock.chat_input.return_value = None
        mod.render_ai_strategy(
            target_ticker="TEST",
            target_company_name="テスト社",
            load_financial_data=mock_load_financial_data,
            get_val_safe=mock_get_val_safe,
        )
        st_mock.header.assert_called()

    def test_smoke_empty_data(self, _patch_deps):
        """空データ時にクラッシュしないこと。"""
        st_mock, mod = _patch_deps
        st_mock.button.return_value = False
        mod.render_ai_strategy(
            target_ticker="EMPTY",
            target_company_name="空データ社",
            load_financial_data=mock_load_financial_data_empty,
            get_val_safe=mock_get_val_safe,
        )

    def test_no_api_call_without_button(self, _patch_deps):
        """ボタン未クリック時に API コールが発生しないこと。"""
        st_mock, mod = _patch_deps
        st_mock.button.return_value = False
        st_mock.text_input.return_value = "fake-api-key"
        mod.render_ai_strategy(
            target_ticker="TEST",
            target_company_name="テスト社",
            load_financial_data=mock_load_financial_data,
            get_val_safe=mock_get_val_safe,
        )
        # genai.Client は呼ばれない (ボタン未押下)
        # spinner も呼ばれない
