"""Tests for orchestrator.py — cost tracking, logging, and model selection logic."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from orchestrator import (
    SkillRouting,
    _confirm_command_execution,
    GROK_COST_PER_1M,
    _extract_usage,
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

    def test_flash_3_8_cost(self) -> None:
        """gemini-3.8-flashのコスト: in=0.75, out=3.75 per 1M tokens (2026-12-31までの価格)."""
        cost = calculate_cost("gemini-3.8-flash", 1_000_000, 1_000_000)
        assert cost == pytest.approx(4.50, rel=1e-4)

    def test_flash_3_6_cost(self) -> None:
        """gemini-3.6-flashのコスト: in=0.75, out=3.75 per 1M tokens."""
        cost = calculate_cost("gemini-3.6-flash", 1_000_000, 1_000_000)
        assert cost == pytest.approx(4.50, rel=1e-4)

    def test_flash_2_5_lite_cost(self) -> None:
        """gemini-2.5-flash-liteのコスト: in=0.10, out=0.40 per 1M tokens."""
        cost = calculate_cost("gemini-2.5-flash-lite", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.50, rel=1e-4)

    def test_flash_lite_uses_its_own_rate_not_flash_rate(self) -> None:
        """flash-liteは'flash'の部分文字列マッチで誤ってflashレートを使わず、
        専用のflash-liteレートを使う('gemini-3.5-flash' は 'gemini-3.5-flash-lite' の部分文字列)"""
        flash_cost = calculate_cost("gemini-3.5-flash", 1_000_000, 1_000_000)
        lite_cost = calculate_cost("gemini-3.5-flash-lite", 1_000_000, 1_000_000)
        assert lite_cost == pytest.approx(2.80, rel=1e-4)
        assert flash_cost == pytest.approx(10.50, rel=1e-4)

    def test_preview_suffix_matches_base_rate(self) -> None:
        """'-preview' 付きのモデル名も基底モデルのレートで計算する。"""
        cost = calculate_cost("gemini-3-flash-preview", 1_000_000, 1_000_000)
        assert cost == pytest.approx(3.50, rel=1e-4)

    def test_grok_uses_runtime_pricing(self) -> None:
        """GrokはAPIから取得した料金表(GROK_COST_PER_1M)で計算する。"""
        with patch.dict(GROK_COST_PER_1M, {"grok-4.7": {"in": 2.00, "out": 6.00}}):
            cost = calculate_cost("grok-4.7", 1_000_000, 1_000_000)
        assert cost == pytest.approx(8.00, rel=1e-4)

    def test_grok_without_pricing_uses_default_rates(self) -> None:
        """料金表を取得できなかったGrokモデルはデフォルトレートを使う。"""
        with patch.dict(GROK_COST_PER_1M, {}, clear=True):
            cost = calculate_cost("grok-4.7", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.50, rel=1e-4)

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
        cost_half = calculate_cost("gemini-2.5-flash-lite", 500_000, 500_000)
        cost_full = calculate_cost("gemini-2.5-flash-lite", 1_000_000, 1_000_000)
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


# ── _extract_usage ───────────────────────────────────────────────────────────

class TestExtractUsage:
    def test_grok_usage_is_normalized(self) -> None:
        """Grok(Responses API)のinput/output_tokensをGemini形式に揃える。"""
        response = MagicMock()
        response.usage.input_tokens = 300
        response.usage.output_tokens = 120
        response.usage.total_tokens = 420
        response.output_text = "grok answer"
        usage, text = _extract_usage(response, "grok-4.3")
        assert (usage.prompt_token_count, usage.candidates_token_count, usage.total_token_count) == (300, 120, 420)
        assert text == "grok answer"

    def test_gemini_thoughts_are_billed_as_output(self) -> None:
        """Geminiの思考トークンは出力単価で課金されるため出力トークンに加算する。"""
        response = MagicMock()
        response.usage_metadata.prompt_token_count = 100
        response.usage_metadata.candidates_token_count = 50
        response.usage_metadata.thoughts_token_count = 30
        response.usage_metadata.total_token_count = 180
        response.text = "gemini answer"
        usage, _ = _extract_usage(response, "gemini-3.8-flash")
        assert usage.candidates_token_count == 80

    def test_gemini_without_thoughts(self) -> None:
        """thoughts_token_countがNone(思考なし)でも落ちない。"""
        response = MagicMock()
        response.usage_metadata.prompt_token_count = 100
        response.usage_metadata.candidates_token_count = 50
        response.usage_metadata.thoughts_token_count = None
        response.usage_metadata.total_token_count = 150
        usage, _ = _extract_usage(response, "gemini-3.8-flash")
        assert usage.candidates_token_count == 50


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

    def test_gemini_3_8_flash_supports_thinking(self) -> None:
        assert _supports_thinking("gemini-3.8-flash") is True

    def test_gemini_3_5_flash_lite_supports_thinking(self) -> None:
        assert _supports_thinking("gemini-3.5-flash-lite") is True

    def test_gemini_2_5_flash_does_not_support_thinking(self) -> None:
        assert _supports_thinking("gemini-2.5-flash") is False


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


# ── run_orchestrator のフォールバック ─────────────────────────────────────────

class TestCrossProviderFallback:
    def _fake_provider(self, name: str, *, fail: bool) -> MagicMock:
        from unittest.mock import AsyncMock
        p = MagicMock()
        p.name = name
        p.supports_cache = name == "gemini"
        p.models = {"Specialist": f"{name}-s", "Primary": f"{name}-p", "Utility": f"{name}-u"}
        p.quick = AsyncMock(side_effect=Exception("routing down"))
        err = Exception(f"{name} down")
        p.agent = AsyncMock(side_effect=err if fail else None)
        p.simple = AsyncMock(side_effect=err) if fail else AsyncMock(return_value="ok-response")
        p.text_of = MagicMock(return_value=f"answer from {name}")
        return p

    def _run(self, gemini_fail: bool, grok: MagicMock | None, gemini_text: str = "answer from gemini") -> tuple[str | None, list[str]]:
        import asyncio
        from unittest.mock import AsyncMock

        import orchestrator
        gemini = self._fake_provider("gemini", fail=gemini_fail)
        gemini.text_of.return_value = gemini_text
        built: list[str] = []

        def build(name: str) -> MagicMock | None:
            built.append(name)
            return gemini if name == "gemini" else grok

        mcp = MagicMock()
        mcp.initialize = AsyncMock()
        mcp.close = AsyncMock()
        with patch.object(orchestrator, "build_provider", side_effect=build), \
             patch.object(orchestrator, "MCPManager", return_value=mcp), \
             patch.object(orchestrator, "print_usage", return_value=0.0), \
             patch.object(orchestrator, "load_dotenv"):
            result = asyncio.run(orchestrator.run_orchestrator("hello", provider="gemini"))
        return result, built

    def test_falls_back_to_other_provider_when_all_gemini_fail(self) -> None:
        """Geminiのメイン・同一プロバイダ内フォールバックが両方失敗したらGrokのPrimaryで答える。"""
        grok = self._fake_provider("grok", fail=False)
        result, built = self._run(gemini_fail=True, grok=grok)
        assert result == "answer from grok"
        assert built == ["gemini", "grok"]
        grok.simple.assert_awaited_once()
        assert grok.simple.call_args.args[0] == "grok-p"

    def test_reports_failure_without_other_provider_key(self) -> None:
        """もう一方のAPIキーが無ければエラーメッセージを返す。"""
        result, _ = self._run(gemini_fail=True, grok=None)
        assert result is not None and "No API key" in result

    def test_no_cross_provider_call_when_main_succeeds(self) -> None:
        """メインが成功すればもう一方のプロバイダは作らない。"""
        result, built = self._run(gemini_fail=False, grok=self._fake_provider("grok", fail=False))
        assert result == "answer from gemini"
        assert built == ["gemini"]

    def test_empty_answer_triggers_fallback(self) -> None:
        """Geminiが例外なしで空の本文を返した場合も失敗扱いにし、Grokへ切り替える。"""
        grok = self._fake_provider("grok", fail=False)
        result, built = self._run(gemini_fail=False, grok=grok, gemini_text="  ")
        assert result == "answer from grok"
        assert built == ["gemini", "grok"]

    def test_max_turns_reached_triggers_fallback(self) -> None:
        """ツール呼び出しが続いてターン上限に達した(agentがNoneを返した)場合もフォールバックに進む。"""
        from unittest.mock import AsyncMock
        grok = self._fake_provider("grok", fail=False)
        import orchestrator
        gemini = self._fake_provider("gemini", fail=False)
        gemini.agent = AsyncMock(return_value=None)
        gemini.simple = AsyncMock(side_effect=Exception("gemini down"))
        mcp = MagicMock()
        mcp.initialize = AsyncMock()
        mcp.close = AsyncMock()
        import asyncio
        with patch.object(orchestrator, "build_provider", side_effect=lambda n: gemini if n == "gemini" else grok),              patch.object(orchestrator, "MCPManager", return_value=mcp),              patch.object(orchestrator, "print_usage", return_value=0.0),              patch.object(orchestrator, "load_dotenv"):
            result = asyncio.run(orchestrator.run_orchestrator("hello", provider="gemini"))
        gemini.simple.assert_awaited_once()
        assert result == "answer from grok"
