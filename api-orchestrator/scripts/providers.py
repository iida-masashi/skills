"""プロバイダ (Gemini / Grok) ごとのAPI呼び出し差分を吸収する層。
どちらも同じメソッド (quick / agent / simple / text_of) を持ち、orchestrator.py は
プロバイダを意識せずに呼び出せる。

track は orchestrator.py から渡されるコールバックで、レスポンスごとのトークン数と
コストを記録する: track(response, model_name, prompt, label) -> None
"""
import json
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import types
from openai import AsyncOpenAI
from pydantic import BaseModel
from scout import XAI_BASE_URL
from tenacity import retry, stop_after_attempt, wait_exponential

Track = Callable[..., None]

# 指数的バックオフで最大3回リトライする (429や一時的な通信エラー対策)
_with_retry = retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)


def _supports_thinking(model_name: str) -> bool:
    """Gemini 3系(3.x)はThinking対応、旧2.x系は非対応という現状の世代境界で判定する"""
    return "gemini-3" in model_name


class GeminiProvider:
    name = "gemini"
    supports_cache = True

    def __init__(self, api_key: str, models: dict[str, str]):
        self.client = genai.Client(api_key=api_key, vertexai=False)
        self.models = models

    @staticmethod
    def text_of(response: Any) -> str:
        return response.text or ""

    @_with_retry
    async def _generate(self, model: str, contents: Any, config: types.GenerateContentConfig) -> Any:
        return await self.client.aio.models.generate_content(model=model, contents=contents, config=config)

    def _output_config(self, enforce_json: bool, response_schema: type[BaseModel] | None, grounding: bool) -> dict[str, Any]:
        # Gemini 3 は temperature を既定値 1.0 から下げるとループや品質低下を起こしうる
        # (公式ガイダンス) ため、temperature は指定しない
        config_args: dict[str, Any] = {}
        if enforce_json or response_schema:
            config_args["response_mime_type"] = "application/json"
            if response_schema:
                config_args["response_schema"] = response_schema
        if grounding:
            config_args["tools"] = [{"google_search": {}}]
        return config_args

    async def quick(self, model: str, prompt: str, response_schema: type[BaseModel] | None = None) -> Any:
        """圧縮・ルーティング・コマンド生成などの単発呼び出し"""
        config = types.GenerateContentConfig(**self._output_config(False, response_schema, False))
        return await self._generate(model, prompt, config)

    async def simple(self, model: str, prompt: str, *, enforce_json: bool, response_schema: type[BaseModel] | None, grounding: bool) -> Any:
        """フォールバック用の単発呼び出し。thinking_config自体が失敗原因だった可能性を考慮し付与しない"""
        config = types.GenerateContentConfig(**self._output_config(enforce_json, response_schema, grounding))
        return await self._generate(model, prompt, config)

    def create_cache(self, model: str, file_path: str) -> str:
        uploaded_file = self.client.files.upload(file=file_path)
        cache = self.client.caches.create(
            model=model,
            config=types.CreateCacheConfig(contents=[uploaded_file], ttl="300s"),
        )
        return cache.name

    async def agent(
        self,
        model: str,
        prompt: str,
        *,
        complex_task: bool,
        enforce_json: bool,
        response_schema: type[BaseModel] | None,
        grounding: bool,
        mcp_manager: Any,
        max_turns: int,
        track: Track,
        cache_name: str | None = None,
    ) -> Any | None:
        """MCPツール呼び出しループ。最終レスポンスを返し、max_turns到達時はNoneを返す"""
        config_args = self._output_config(enforce_json, response_schema, grounding)
        if _supports_thinking(model):
            # gemini-3.8-flash は MINIMAL を400で拒否するため、軽いタスクも LOW にする
            config_args["thinking_config"] = types.ThinkingConfig(
                include_thoughts=True,
                thinking_level="high" if complex_task else "low",
            )
        mcp_tools = mcp_manager.get_gemini_tools()
        if mcp_tools:
            config_args.setdefault("tools", []).extend(mcp_tools)
            if grounding:
                # 組み込みツール (google_search) と関数呼び出しを併用するには明示的な許可が必要 (無いと400)
                config_args["tool_config"] = types.ToolConfig(include_server_side_tool_invocations=True)
        if cache_name:
            config_args["cached_content"] = cache_name
        config = types.GenerateContentConfig(**config_args)

        history = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        for turn in range(1, max_turns + 1):
            response = await self._generate(model, history, config)
            if not response.function_calls:
                return response
            track(response, model, prompt, f"Turn {turn}/{max_turns}")
            # thought_signature を保持するため、モデルの応答をそのまま履歴に追加する
            history.append(response.candidates[0].content)
            parts = []
            for fc in response.function_calls:
                result_text = await mcp_manager.call_tool(fc.name, fc.args)
                parts.append(types.Part.from_function_response(name=fc.name, response={"result": result_text}))
            history.append(types.Content(role="user", parts=parts))
        return None


class GrokProvider:
    """xAI の Responses API (/v1/responses) を OpenAI SDK 経由で呼ぶ。
    Web検索 (web_search) はサーバー側ツールとして Responses API でのみ使える"""
    name = "grok"
    supports_cache = False

    def __init__(self, api_key: str, models: dict[str, str]):
        self.client = AsyncOpenAI(api_key=api_key, base_url=XAI_BASE_URL)
        self.models = models

    @staticmethod
    def text_of(response: Any) -> str:
        return response.output_text or ""

    @_with_retry
    async def _generate(self, **kwargs: Any) -> Any:
        return await self.client.responses.create(**kwargs)

    @staticmethod
    def _text_format(enforce_json: bool, response_schema: type[BaseModel] | None) -> dict[str, Any] | None:
        if response_schema:
            return {"format": {"type": "json_schema", "name": response_schema.__name__, "schema": response_schema.model_json_schema()}}
        if enforce_json:
            return {"format": {"type": "json_object"}}
        return None

    def _request(self, model: str, input_: Any, *, enforce_json: bool, response_schema: type[BaseModel] | None, tools: list[dict]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model": model, "input": input_}
        text_format = self._text_format(enforce_json, response_schema)
        if text_format:
            kwargs["text"] = text_format
        if tools:
            kwargs["tools"] = tools
        return kwargs

    async def quick(self, model: str, prompt: str, response_schema: type[BaseModel] | None = None) -> Any:
        return await self._generate(**self._request(model, prompt, enforce_json=False, response_schema=response_schema, tools=[]))

    async def simple(self, model: str, prompt: str, *, enforce_json: bool, response_schema: type[BaseModel] | None, grounding: bool) -> Any:
        tools = [{"type": "web_search"}] if grounding else []
        return await self._generate(**self._request(model, prompt, enforce_json=enforce_json, response_schema=response_schema, tools=tools))

    async def agent(
        self,
        model: str,
        prompt: str,
        *,
        complex_task: bool,
        enforce_json: bool,
        response_schema: type[BaseModel] | None,
        grounding: bool,
        mcp_manager: Any,
        max_turns: int,
        track: Track,
        cache_name: str | None = None,
    ) -> Any | None:
        """MCPツール呼び出しループ。complex_task はモデル選択 (Specialist) で反映済みなのでここでは使わない"""
        tools: list[dict] = [{"type": "web_search"}] if grounding else []
        tools.extend(mcp_manager.get_openai_tools())

        input_items: list[Any] = [{"role": "user", "content": prompt}]
        for turn in range(1, max_turns + 1):
            response = await self._generate(**self._request(model, input_items, enforce_json=enforce_json, response_schema=response_schema, tools=tools))
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                return response
            track(response, model, prompt, f"Turn {turn}/{max_turns}")
            # 推論・検索・関数呼び出しの出力項目をそのまま入力に戻し、続きを生成させる
            input_items.extend(item.model_dump(exclude_none=True) for item in response.output)
            for call in calls:
                result_text = await mcp_manager.call_tool(call.name, json.loads(call.arguments or "{}"))
                input_items.append({"type": "function_call_output", "call_id": call.call_id, "output": result_text})
        return None
