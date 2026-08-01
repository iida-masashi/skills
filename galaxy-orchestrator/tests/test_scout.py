"""Tests for scout.py — model discovery and categorization logic."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

scripts_dir = str(Path(__file__).parent.parent / "scripts")
sys.path.insert(0, scripts_dir)

# test_orchestrator.py が先に実行されると sys.modules["scout"] が stub になるため、
# 本物の scout を "scout_real" という名前で importlib でロードして sys.modules に登録する。
import importlib
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "scout_real",
    str(Path(__file__).parent.parent / "scripts" / "scout.py"),
)
_scout_real = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["scout_real"] = _scout_real  # @patch("scout_real.xxx") のために登録
_spec.loader.exec_module(_scout_real)  # type: ignore[union-attr]

get_best_available_models = _scout_real.get_best_available_models
scout_models = _scout_real.scout_models


def _make_model(name: str, display_name: str = "") -> MagicMock:
    m = MagicMock()
    m.name = f"models/{name}"
    m.display_name = display_name or name
    return m


# ── get_best_available_models ─────────────────────────────────────────────────

_SCOUT_MODULE = "scout_real"  # importlib でロードした本物モジュールのパス


class TestGetBestAvailableModels:
    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_returns_none_when_no_api_key(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """APIキーが未設定のときNoneを返す。"""
        with patch.dict("os.environ", {}, clear=True):
            result = get_best_available_models()
        assert result is None

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_detects_3_1_pro_as_specialist(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """gemini-3.1-proモデルをSpecialistとして選択する。"""
        mock_instance = MagicMock()
        mock_instance.models.list.return_value = [
            _make_model("gemini-3.1-pro-preview"),
            _make_model("gemini-2.0-flash"),
            _make_model("gemini-3.1-flash-lite-preview"),
        ]
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "dummy-key"}, clear=True):
            result = get_best_available_models()

        assert result is not None
        assert "3.1-pro" in result["Specialist"]

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_detects_3_6_flash_as_primary(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """gemini-3.6-flashモデルをPrimaryとして選択する(3.1-flashより優先)。"""
        mock_instance = MagicMock()
        mock_instance.models.list.return_value = [
            _make_model("gemini-3.1-pro-preview"),
            _make_model("gemini-3.1-flash-preview"),
            _make_model("gemini-3.6-flash"),
            _make_model("gemini-3.5-flash-lite"),
        ]
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "dummy-key"}, clear=True):
            result = get_best_available_models()

        assert result is not None
        assert result["Primary"] == "gemini-3.6-flash"

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_detects_3_5_flash_lite_as_utility(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """gemini-3.5-flash-liteモデルをUtilityとして選択する(3.1-flash-liteより優先)。"""
        mock_instance = MagicMock()
        mock_instance.models.list.return_value = [
            _make_model("gemini-3.1-pro-preview"),
            _make_model("gemini-3.1-flash-lite-preview"),
            _make_model("gemini-3.5-flash-lite"),
        ]
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "dummy-key"}, clear=True):
            result = get_best_available_models()

        assert result is not None
        assert result["Utility"] == "gemini-3.5-flash-lite"

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_detects_flash_lite_as_utility(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """gemini-3.1-flash-liteモデルをUtilityとして選択する。"""
        mock_instance = MagicMock()
        mock_instance.models.list.return_value = [
            _make_model("gemini-3.1-pro-preview"),
            _make_model("gemini-2.0-flash"),
            _make_model("gemini-3.1-flash-lite-preview"),
        ]
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "dummy-key"}, clear=True):
            result = get_best_available_models()

        assert result is not None
        assert "flash-lite" in result["Utility"]

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_returns_none_on_exception(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """APIエラー時にNoneを返す（デフォルトへのフォールバックは呼び出し元の責務）。"""
        mock_instance = MagicMock()
        mock_instance.models.list.side_effect = Exception("API error")
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "dummy-key"}, clear=True):
            result = get_best_available_models()

        assert result is None

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_returns_all_three_categories(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """結果にSpecialist, Primary, Utility の3カテゴリが含まれる。"""
        mock_instance = MagicMock()
        mock_instance.models.list.return_value = [
            _make_model("gemini-3.1-pro-preview"),
            _make_model("gemini-3.1-flash-preview"),
            _make_model("gemini-3.1-flash-lite-preview"),
        ]
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "dummy-key"}, clear=True):
            result = get_best_available_models()

        assert result is not None
        assert set(result.keys()) == {"Specialist", "Primary", "Utility"}

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_accepts_gemini_api_key_env(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """GEMINI_API_KEY環境変数でも動作する（Clientが呼ばれる）。"""
        mock_instance = MagicMock()
        mock_instance.models.list.return_value = [_make_model("gemini-3.1-pro-preview")]
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GEMINI_API_KEY": "gemini-key"}, clear=True):
            get_best_available_models()

        assert mock_client.called


# ── scout_models ──────────────────────────────────────────────────────────────

class TestScoutModels:
    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_returns_error_without_api_key(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """APIキーなしのときエラーメッセージを返す。"""
        with patch.dict("os.environ", {}, clear=True):
            result = scout_models()
        assert "Error" in result or "error" in result.lower()

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_report_contains_model_names(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """レポートに取得したモデル名が含まれる。"""
        mock_instance = MagicMock()
        mock_instance.models.list.return_value = [
            _make_model("gemini-3.1-pro-preview", "Gemini 3.1 Pro"),
            _make_model("gemini-2.0-flash", "Gemini 2.0 Flash"),
        ]
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "dummy"}, clear=True):
            result = scout_models()

        assert "gemini-3.1-pro-preview" in result
        assert "gemini-2.0-flash" in result

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_keyword_filter_works(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """keywordフィルタが機能する: 一致しないモデルは除外される。"""
        mock_instance = MagicMock()
        mock_instance.models.list.return_value = [
            _make_model("gemini-3.1-pro-preview"),
            _make_model("gemini-2.0-flash"),
        ]
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "dummy"}, clear=True):
            result = scout_models(keyword="pro")

        assert "pro-preview" in result
        assert "2.0-flash" not in result

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_no_match_returns_error_message(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """キーワード一致なしのとき、エラーメッセージを返す。"""
        mock_instance = MagicMock()
        mock_instance.models.list.return_value = [_make_model("gemini-2.0-flash")]
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "dummy"}, clear=True):
            result = scout_models(keyword="nonexistent-xyz")

        assert "No models found" in result or "❌" in result

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_report_categorizes_specialist(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """Specialist (3.1-pro) が正しいカテゴリでレポートに含まれる。"""
        mock_instance = MagicMock()
        mock_instance.models.list.return_value = [
            _make_model("gemini-3.1-pro-preview"),
        ]
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "dummy"}, clear=True):
            result = scout_models()

        assert "Specialist" in result

    @patch("scout_real.genai.Client")
    @patch("scout_real.load_dotenv")
    def test_api_error_returns_error_string(self, mock_dotenv: MagicMock, mock_client: MagicMock) -> None:
        """APIエラー時にエラー文字列を返す（クラッシュしない）。"""
        mock_instance = MagicMock()
        mock_instance.models.list.side_effect = Exception("Connection refused")
        mock_client.return_value = mock_instance

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "dummy"}, clear=True):
            result = scout_models()

        assert "Error" in result or "error" in result.lower()
