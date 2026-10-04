"""Tests for providers.py — Gemini/Grok のリクエスト組み立てとツール呼び出しループ。"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from providers import GeminiProvider, GrokProvider  # noqa: E402
from pydantic import BaseModel  # noqa: E402


class _Answer(BaseModel):
    city: str


def _item(item_type: str, **fields: object) -> MagicMock:
    item = MagicMock()
    item.type = item_type
    for k, v in fields.items():
        setattr(item, k, v)
    item.model_dump.return_value = {"type": item_type, **fields}
    return item


def _mcp(tools: list[dict] | None = None) -> MagicMock:
    mcp = MagicMock()
    mcp.get_openai_tools.return_value = tools or []
    mcp.get_gemini_tools.return_value = []
    mcp.call_tool = AsyncMock(return_value="42")
    return mcp


def _grok() -> GrokProvider:
    provider = GrokProvider("dummy", {"Specialist": "grok-4.7", "Primary": "grok-4.3", "Utility": "grok-4.20-0309-non-reasoning"})
    provider._generate = AsyncMock()  # type: ignore[method-assign]
    return provider


class TestGrokAgentLoop:
    def test_function_call_round_trip(self) -> None:
        """function_call を受けたらMCPツールを実行し、call_id付きの結果を返して最終回答を得る。"""
        provider = _grok()
        call = _item("function_call", name="get_stock", arguments='{"sku": "A1"}', call_id="call-1")
        final = SimpleNamespace(output=[_item("message")], output_text="在庫は42個")
        provider._generate.side_effect = [SimpleNamespace(output=[call]), final]
        mcp = _mcp([{"type": "function", "name": "get_stock", "parameters": {"type": "object", "properties": {}}}])
        track = MagicMock()

        result = asyncio.run(provider.agent(
            "grok-4.3", "SKU A1 の在庫は？", complex_task=False, enforce_json=False, response_schema=None,
            grounding=True, mcp_manager=mcp, max_turns=8, track=track,
        ))

        assert result is final
        mcp.call_tool.assert_awaited_once_with("get_stock", {"sku": "A1"})
        second_input = provider._generate.call_args_list[1].kwargs["input"]
        assert second_input[-1] == {"type": "function_call_output", "call_id": "call-1", "output": "42"}
        assert {"type": "function_call", "name": "get_stock", "arguments": '{"sku": "A1"}', "call_id": "call-1"} in second_input
        tools = provider._generate.call_args_list[0].kwargs["tools"]
        assert tools[0] == {"type": "web_search"}
        assert tools[1]["name"] == "get_stock"
        track.assert_called_once()

    def test_returns_none_when_max_turns_reached(self) -> None:
        """ツール呼び出しが続いて上限に達したらNoneを返す。"""
        provider = _grok()
        call = _item("function_call", name="t", arguments="{}", call_id="c")
        provider._generate.return_value = SimpleNamespace(output=[call])

        result = asyncio.run(provider.agent(
            "grok-4.3", "p", complex_task=False, enforce_json=False, response_schema=None,
            grounding=False, mcp_manager=_mcp(), max_turns=2, track=MagicMock(),
        ))

        assert result is None
        assert provider._generate.await_count == 2

    def test_no_tools_key_when_no_tools(self) -> None:
        """ツールが1つも無いときは tools を送らない。"""
        provider = _grok()
        provider._generate.return_value = SimpleNamespace(output=[_item("message")], output_text="ok")

        asyncio.run(provider.agent(
            "grok-4.3", "p", complex_task=False, enforce_json=False, response_schema=None,
            grounding=False, mcp_manager=_mcp(), max_turns=1, track=MagicMock(),
        ))

        assert "tools" not in provider._generate.call_args.kwargs


class TestGrokTextFormat:
    def test_pydantic_schema_becomes_json_schema(self) -> None:
        fmt = GrokProvider._text_format(False, _Answer)
        assert fmt["format"]["type"] == "json_schema"
        assert fmt["format"]["name"] == "_Answer"
        assert fmt["format"]["schema"]["properties"]["city"]["type"] == "string"

    def test_enforce_json_without_schema(self) -> None:
        assert GrokProvider._text_format(True, None) == {"format": {"type": "json_object"}}

    def test_plain_text(self) -> None:
        assert GrokProvider._text_format(False, None) is None


class TestGeminiAgent:
    def _run(self, model: str, complex_task: bool, grounding: bool = False, gemini_tools: list | None = None) -> object:
        provider = GeminiProvider("dummy", {"Specialist": "gemini-3.1-pro-preview", "Primary": "gemini-3.8-flash", "Utility": "gemini-3.5-flash-lite"})
        response = MagicMock()
        response.function_calls = None
        provider._generate = AsyncMock(return_value=response)  # type: ignore[method-assign]
        mcp = _mcp()
        mcp.get_gemini_tools.return_value = gemini_tools or []
        asyncio.run(provider.agent(
            model, "p", complex_task=complex_task, enforce_json=False, response_schema=None,
            grounding=grounding, mcp_manager=mcp, max_turns=1, track=MagicMock(),
        ))
        return provider._generate.call_args.args[2]

    def test_primary_uses_low_thinking(self) -> None:
        """gemini-3.8-flash は MINIMAL を400で拒否するため、軽いタスクは LOW を使う。"""
        config = self._run("gemini-3.8-flash", complex_task=False)
        assert config.thinking_config.thinking_level.value.lower() == "low"

    def test_specialist_uses_high_thinking(self) -> None:
        config = self._run("gemini-3.1-pro-preview", complex_task=True)
        assert config.thinking_config.thinking_level.value.lower() == "high"

    def test_no_thinking_for_gemini_2(self) -> None:
        config = self._run("gemini-2.5-flash", complex_task=False)
        assert config.thinking_config is None

    def test_temperature_not_lowered(self) -> None:
        """Gemini 3 では temperature を既定値1.0から下げない(指定しない)。"""
        config = self._run("gemini-3.8-flash", complex_task=False)
        assert config.temperature is None

    def test_search_with_mcp_tools_enables_server_side_invocations(self) -> None:
        """google_search と MCP の関数ツールを併用するときは include_server_side_tool_invocations を付ける(無いと400)。"""
        tools = [{"function_declarations": [{"name": "get_stock", "description": "", "parameters": {"type": "object", "properties": {}}}]}]
        config = self._run("gemini-3.8-flash", complex_task=False, grounding=True, gemini_tools=tools)
        assert config.tool_config.include_server_side_tool_invocations is True

    def test_search_only_has_no_tool_config(self) -> None:
        config = self._run("gemini-3.8-flash", complex_task=False, grounding=True)
        assert config.tool_config is None
