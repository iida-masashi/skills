"""Tests for orchestrator.py — cost tracking, logging, and model selection logic."""
import json
import sys
import types as _types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# scout をモックしてからインポート（APIキー不要にする）
# conftest ではなくモジュール先頭で差し込む。pytest セッション内で scout が
# まだロードされていない場合のみ stub を登録することで test_scout.py と衝突しない。
if "scout" not in sys.modules:
    _scout_stub = _types.ModuleType("scout")
    _scout_stub.get_best_available_models = MagicMock(return_value={  # type: ignore[attr-defined]
        "Specialist": "gemini-3.1-pro-preview",
        "Primary": "gemini-2.0-flash",
        "Utility": "gemini-3.1-flash-lite-preview",
    })
    sys.modules["scout"] = _scout_stub

from orchestrator import (
    SkillRouting,
    _confirm_command_execution,
    _supports_thinking,
    calculate_cost,
    log_usage,
    print_usage,
)

# ── calculate_cost ───────────────────────────────────────────────────────────

class TestCalculateCost:
    def test_pro_model_cost(self) -> None:
        """gemini-3.1-proのコスト計算: in=2.00, out=12.00 per 1M tokens."""
        cost = calculate_cost("gemini-3.1-pro-preview", 1_000_000, 1_000_000)
        assert cost == pytest.approx(14.00, rel=1e-4)

    def test_flash_model_cost(self) -> None:
        """gemini-3.1-flashのコスト: in=0.075, out=0.30 per 1M tokens."""
        cost = calculate_cost("gemini-3.1-flash", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.375, rel=1e-4)

    def test_flash_2_0_model_cost(self) -> None:
        """gemini-2.0-flashのコスト: in=0.10, out=0.40 per 1M tokens."""
        cost = calculate_cost("gemini-2.0-flash", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.50, rel=1e-4)

    def test_flash_3_6_cost(self) -> None:
        """gemini-3.6-flashのコスト: in=1.50, out=7.50 per 1M tokens."""
        cost = calculate_cost("gemini-3.6-flash", 1_000_000, 1_000_000)
        assert cost == pytest.approx(9.00, rel=1e-4)

    def test_flash_lite_uses_its_own_rate_not_flash_rate(self) -> None:
        """flash-liteは'flash'の部分文字列マッチで誤ってflashレートを使わず、
        専用のflash-liteレートを使う(過去のバグ: 'gemini-3.1-flash' が
        'gemini-3.1-flash-lite-preview' の部分文字列としてマッチしていた)"""
        flash_cost = calculate_cost("gemini-3.1-flash", 1_000_000, 1_000_000)
        lite_cost = calculate_cost("gemini-3.1-flash-lite-preview", 1_000_000, 1_000_000)
        assert lite_cost != flash_cost
        assert lite_cost == pytest.approx(1.75, rel=1e-4)
        assert flash_cost == pytest.approx(0.375, rel=1e-4)

    def test_flash_lite_3_5_cost(self) -> None:
        """gemini-3.5-flash-liteのコスト: in=0.25, out=1.50 per 1M tokens."""
        cost = calculate_cost("gemini-3.5-flash-lite", 1_000_000, 1_000_000)
        assert cost == pytest.approx(1.75, rel=1e-4)

    def test_unknown_model_uses_default_rates(self) -> None:
        """未知のモデルはデフォルトレート(in=0.10, out=0.40)を使う。"""
        cost = calculate_cost("unknown-model-xyz", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.50, rel=1e-4)

    def test_zero_tokens_zero_cost(self) -> None:
        """トークン0のときコストは0。"""
        cost = calculate_cost("gemini-3.1-pro-preview", 0, 0)
        assert cost == 0.0

    def test_cost_proportional_to_tokens(self) -> None:
        """コストはトークン数に比例する。"""
        cost_half = calculate_cost("gemini-2.0-flash", 500_000, 500_000)
        cost_full = calculate_cost("gemini-2.0-flash", 1_000_000, 1_000_000)
        assert cost_full == pytest.approx(cost_half * 2, rel=1e-4)

    def test_input_output_rates_differ(self) -> None:
        """inputとoutputのレートが異なることを確認（output > input）。"""
        cost_in_only = calculate_cost("gemini-3.1-pro-preview", 1_000_000, 0)
        cost_out_only = calculate_cost("gemini-3.1-pro-preview", 0, 1_000_000)
        assert cost_out_only > cost_in_only


# ── log_usage ────────────────────────────────────────────────────────────────

class TestLogUsage:
    def test_log_creates_jsonl_entry(self, tmp_path: Path) -> None:
        """usage_log.jsonlに正しいJSONLエントリが書き込まれる。"""
        log_file = tmp_path / "usage_log.jsonl"

        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 100
        mock_usage.candidates_token_count = 50
        mock_usage.total_token_count = 150

        with patch("orchestrator.os.path.join", return_value=str(log_file)):
            log_usage(
                model_name="gemini-2.0-flash",
                prompt="テストプロンプト",
                response_text="テスト応答",
                usage=mock_usage,
                cost=0.000123,
                routing={"recommended_skill": "consultant-toolkit"},
            )

        assert log_file.exists()
        entry = json.loads(log_file.read_text(encoding="utf-8"))
        assert entry["model"] == "gemini-2.0-flash"
        assert entry["prompt_tokens"] == 100
        assert entry["candidates_tokens"] == 50
        assert entry["cost_usd"] == pytest.approx(0.000123)
        assert entry["routing"]["recommended_skill"] == "consultant-toolkit"

    def test_log_entry_has_timestamp(self, tmp_path: Path) -> None:
        """タイムスタンプがISO形式で含まれる。"""
        log_file = tmp_path / "usage_log.jsonl"

        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 10
        mock_usage.candidates_token_count = 10
        mock_usage.total_token_count = 20

        with patch("orchestrator.os.path.join", return_value=str(log_file)):
            log_usage("model", "prompt", "response", mock_usage, 0.0)

        entry = json.loads(log_file.read_text(encoding="utf-8"))
        assert "T" in entry["timestamp"]  # ISO 8601形式

    def test_log_appends_multiple_entries(self, tmp_path: Path) -> None:
        """複数回呼び出すとJSONLに複数エントリが追加される。"""
        log_file = tmp_path / "usage_log.jsonl"

        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 10
        mock_usage.candidates_token_count = 10
        mock_usage.total_token_count = 20

        with patch("orchestrator.os.path.join", return_value=str(log_file)):
            for i in range(3):
                log_usage(f"model-{i}", "p", "r", mock_usage, 0.0)

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

    def test_log_handles_write_error_gracefully(self) -> None:
        """ファイル書き込みエラー時にクラッシュしない。"""
        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 10
        mock_usage.candidates_token_count = 10
        mock_usage.total_token_count = 20

        with patch("builtins.open", side_effect=PermissionError("denied")):
            # 例外が伝播しないことを確認
            log_usage("model", "prompt", "response", mock_usage, 0.0)


# ── print_usage ───────────────────────────────────────────────────────────────

class TestPrintUsage:
    def test_returns_cost_when_metadata_available(self, capsys: pytest.CaptureFixture) -> None:
        """usage_metadataがある場合、コストを返す。"""
        mock_response = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 1_000_000
        mock_response.usage_metadata.candidates_token_count = 1_000_000
        mock_response.usage_metadata.total_token_count = 2_000_000
        mock_response.text = "テスト応答"

        with patch("orchestrator.log_usage"):
            cost = print_usage(mock_response, "gemini-2.0-flash", "prompt")

        assert cost == pytest.approx(0.50, rel=1e-4)

    def test_returns_zero_when_no_metadata(self, capsys: pytest.CaptureFixture) -> None:
        """usage_metadataがない場合、0を返す。"""
        mock_response = MagicMock()
        mock_response.usage_metadata = None

        cost = print_usage(mock_response, "gemini-2.0-flash", "prompt")
        assert cost == 0.0

    def test_prints_token_info(self, capsys: pytest.CaptureFixture) -> None:
        """トークン情報が標準出力に表示される。"""
        mock_response = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 500
        mock_response.usage_metadata.candidates_token_count = 200
        mock_response.usage_metadata.total_token_count = 700
        mock_response.text = "response"

        with patch("orchestrator.log_usage"):
            print_usage(mock_response, "gemini-2.0-flash", "prompt")

        captured = capsys.readouterr()
        assert "500" in captured.out
        assert "200" in captured.out


# ── SkillRouting schema ───────────────────────────────────────────────────────

class TestSkillRoutingSchema:
    def test_valid_routing(self) -> None:
        """有効なルーティングデータをパースできる。"""
        routing = SkillRouting(
            recommended_skill="consultant-toolkit",
            reason="Financial analytics requested",
        )
        assert routing.recommended_skill == "consultant-toolkit"
        assert len(routing.reason) > 0

    def test_none_routing(self) -> None:
        """'none' も有効なskill値として受け付ける。"""
        routing = SkillRouting(recommended_skill="none", reason="No matching skill")
        assert routing.recommended_skill == "none"

    def test_missing_field_raises(self) -> None:
        """必須フィールドが欠けているとValidationError。"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SkillRouting(recommended_skill="consultant-toolkit")  # type: ignore[call-arg]


# ── _supports_thinking ─────────────────────────────────────────────────────────

class TestSupportsThinking:
    def test_gemini_3_1_pro_supports_thinking(self) -> None:
        assert _supports_thinking("gemini-3.1-pro-preview") is True

    def test_gemini_3_6_flash_supports_thinking(self) -> None:
        assert _supports_thinking("gemini-3.6-flash") is True

    def test_gemini_3_5_flash_lite_supports_thinking(self) -> None:
        assert _supports_thinking("gemini-3.5-flash-lite") is True

    def test_gemini_2_0_flash_does_not_support_thinking(self) -> None:
        assert _supports_thinking("gemini-2.0-flash") is False


# ── _confirm_command_execution ──────────────────────────────────────────────────

class TestConfirmCommandExecution:
    def test_auto_confirm_true_skips_prompt(self) -> None:
        """auto_confirm=Trueなら入力を求めずTrueを返す。"""
        assert _confirm_command_execution("echo hi", auto_confirm=True) is True

    def test_non_interactive_without_auto_confirm_refuses(self) -> None:
        """非対話環境(isatty=False)でauto_confirmもFalseなら実行を拒否する。"""
        with patch("orchestrator.sys.stdin.isatty", return_value=False):
            assert _confirm_command_execution("echo hi", auto_confirm=False) is False

    def test_interactive_yes_confirms(self) -> None:
        """対話環境で'y'と入力すればTrueを返す。"""
        with patch("orchestrator.sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="y"):
            assert _confirm_command_execution("echo hi", auto_confirm=False) is True

    def test_interactive_no_refuses(self) -> None:
        """対話環境で'n'または空入力ならFalseを返す。"""
        with patch("orchestrator.sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="n"):
            assert _confirm_command_execution("echo hi", auto_confirm=False) is False
