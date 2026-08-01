import asyncio
import json
import os
import subprocess
import sys
import time
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Model Scout から最新の戦力リストを取得
from mcp_manager import MCPManager
from scout import get_best_available_models
from tenacity import retry, stop_after_attempt, wait_exponential

# --- Pydantic Schemas for Structured Output ---
class SkillRouting(BaseModel):
    recommended_skill: str = Field(description="The most appropriate skill for the task (e.g., darts-forecast-skill, opendata-skill, consultant-toolkit, python-safe-coding, or none)")
    reason: str = Field(description="Reason for recommending this skill")

# --- 1. Token & Cost Tracker Constants ---
# 料金は https://ai.google.dev/gemini-api/docs/pricing (有料枠) の1Mトークン単価(USD)。
# 取得日 2026-08-01, WebFetch要約経由の調査結果であり公式ページの生HTMLでの一次確認は未実施。
# 特に gemini-3.6-flash の $1.50/$7.50 は旧flashレートの約20倍で、Pro級の価格帯にあたる
# ため、実際にコストが重要な判断に使う前に ai.google.dev/gemini-api/docs/pricing を目視確認すること。
# flash-lite は flash の部分文字列ではないが、将来の命名変更に備えて
# calculate_cost 側でキーを「文字列が長い順」に評価し、最も具体的な一致を優先する
COST_PER_1M_TOKENS = {
    "gemini-3.1-pro": {"in": 2.00, "out": 12.00},
    "gemini-3-pro": {"in": 2.00, "out": 12.00},
    "gemini-3.6-flash": {"in": 1.50, "out": 7.50},
    "gemini-3.5-flash-lite": {"in": 0.25, "out": 1.50},
    "gemini-3.1-flash-lite": {"in": 0.25, "out": 1.50},
    "gemini-3-flash-lite": {"in": 0.25, "out": 1.50},
    "gemini-3.1-flash": {"in": 0.075, "out": 0.30},
    "gemini-3-flash": {"in": 0.075, "out": 0.30},
    "gemini-2.0-flash": {"in": 0.10, "out": 0.40},
}

def calculate_cost(model_name: str, prompt_tokens: int, candidates_tokens: int) -> float:
    """トークン数から概算コスト（USD）を計算する"""
    rate_in, rate_out = 0.0, 0.0
    # キー文字列が長い(=より具体的な)順に評価する。"flash-lite" は "flash" の
    # 部分文字列ではないため実害はないが、将来似た命名が増えても誤マッチしないための保険
    for k in sorted(COST_PER_1M_TOKENS, key=len, reverse=True):
        if k in model_name:
            rate_in, rate_out = COST_PER_1M_TOKENS[k]["in"], COST_PER_1M_TOKENS[k]["out"]
            break
    if rate_in == 0:
        rate_in, rate_out = 0.10, 0.40

    cost = (prompt_tokens / 1_000_000) * rate_in + (candidates_tokens / 1_000_000) * rate_out
    return cost

from datetime import UTC, datetime  # noqa: E402


def log_usage(model_name: str, prompt: str, response_text: str, usage: Any, cost: float, routing: dict | None = None) -> None:
    """使用状況を JSONL ログファイルに記録するわ"""
    log_file = os.path.join(os.path.dirname(__file__), "..", "usage_log.jsonl")
    log_entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "model": model_name,
        "prompt_snippet": prompt[:100],
        "response_snippet": response_text[:100] if response_text else "",
        "prompt_tokens": usage.prompt_token_count if usage else 0,
        "candidates_tokens": usage.candidates_token_count if usage else 0,
        "total_tokens": usage.total_token_count if usage else 0,
        "cost_usd": cost,
        "routing": routing
    }
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️ Failed to write usage log: {e}")

def print_usage(response: Any, model_name: str, prompt: str, routing: dict | None = None, label: str = "") -> float:
    """レスポンスからトークン使用量とコストを抽出し出力・記録する。
    label はどの呼び出し(圧縮/ルーティング/メイン等)かを示す接頭辞。"""
    prefix = f"[{label}] " if label else ""
    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        p_tokens = response.usage_metadata.prompt_token_count
        c_tokens = response.usage_metadata.candidates_token_count
        t_tokens = response.usage_metadata.total_token_count
        cost = calculate_cost(model_name, p_tokens, c_tokens)
        print(f"📊 {prefix}[Token & Cost Tracker] In: {p_tokens} | Out: {c_tokens} | Total: {t_tokens} | Est. Cost: ${cost:.6f}")
        response_text = response.text if hasattr(response, 'text') else ""
        log_usage(model_name, prompt, response_text, response.usage_metadata, cost, routing)
        return cost
    else:
        print(f"📊 {prefix}[Token & Cost Tracker] Usage metadata not available.")
        return 0.0

# --- 2. Advanced Retry & Backoff ---
@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True
)
async def generate_with_retry_async(client: genai.Client, model: str, contents: Any, config: types.GenerateContentConfig) -> Any:
    """指数的バックオフを用いてAPIコールを非同期でリトライする"""
    return await client.aio.models.generate_content(
        model=model,
        contents=contents,
        config=config
    )

def _supports_thinking(model_name: str) -> bool:
    """Gemini 3系(3.x)はThinking対応、旧2.0系は非対応という現状の世代境界で判定する"""
    return "gemini-3" in model_name

def _confirm_command_execution(cmd: str, auto_confirm: bool = False) -> bool:
    """--auto-run で生成されたコマンドを実行してよいか確認する。
    LLMが生成した文字列を無条件でshell実行しないための安全弁。"""
    if auto_confirm:
        print(f"⚠️ --yes flag set: skipping confirmation for: {cmd}")
        return True
    if not sys.stdin.isatty():
        print("⚠️ Non-interactive session and --yes not set: refusing to execute generated command.")
        return False
    answer = input(f"❓ Execute this generated command? [y/N]: {cmd}\n> ").strip().lower()
    return answer in ("y", "yes")

async def run_orchestrator(
    prompt: str,
    enforce_json: bool = False,
    response_schema: type[BaseModel] | None = None,
    grounding: bool = False,
    auto_run: bool = False,
    auto_run_yes: bool = False,
    cache_file_path: str | None = None,
    max_agentic_turns: int = 8
) -> str | None:
    """
    Galaxy Orchestrator (Gemini 3 Native): MCP 連携による自律型エージェントループ対応版
    """
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ Error: GOOGLE_API_KEY is missing in .env")
        sys.exit(1)

    client = genai.Client(api_key=api_key, vertexai=False)

    best_models = get_best_available_models()
    if not best_models:
        best_models = {
            "Specialist": "gemini-3.1-pro-preview",
            "Primary": "gemini-3.6-flash",
            "Utility": "gemini-3.5-flash-lite"
        }

    # このリクエスト全体(圧縮/ルーティング/コマンド生成/メイン/ループ中間ターンを含む)で
    # 発生した推定コストの合計。print_usage を呼ぶたびに加算する
    total_cost = 0.0

    # MCP Manager Initialization
    mcp_config_path = os.path.join(os.path.dirname(__file__), "..", "mcp_servers.json")
    mcp_manager = MCPManager(mcp_config_path)
    await mcp_manager.initialize()

    # --- 4. Dynamic Context Compression ---
    COMPRESSION_THRESHOLD = 5000
    if len(prompt) > COMPRESSION_THRESHOLD and not cache_file_path:
        print(f"🗜️ Prompt exceeds {COMPRESSION_THRESHOLD} chars ({len(prompt)}). Compressing context with Utility model...")
        try:
            compression_prompt = f"以下の長文コンテキストから、システムプロンプト、要求事項、および数値データを抽出して要約してください:\n\n{prompt}"
            compression_response = await generate_with_retry_async(
                client,
                best_models["Utility"],
                compression_prompt,
                types.GenerateContentConfig(temperature=0.2)
            )
            total_cost += print_usage(compression_response, best_models["Utility"], compression_prompt, label="Compression")
            # 要約されたコンテキストと、失われてはいけない直近のプロンプトを結合。
            # 実際の指示は多くの場合プロンプト末尾に来るため、先頭だけでなく末尾も保持する
            # (元は先頭1000文字のみを残しており、末尾に指示があるケースで消失していた)
            head_len, tail_len = 500, 1000
            if len(prompt) > head_len + tail_len:
                original_excerpt = f"{prompt[:head_len]}\n...[MIDDLE TRUNCATED]...\n{prompt[-tail_len:]}"
            else:
                original_excerpt = prompt
            prompt = f"【要約されたコンテキスト】\n{compression_response.text}\n\n【元の要求（抜粋）】\n{original_excerpt}"
            print("✅ Context dynamically compressed to save tokens.")
        except Exception as e:
            print(f"⚠️ Compression failed, proceeding with original prompt: {e}")

    # --- 5. Skill Dispatcher (Routing) ---
    print("🧭 Analyzing intent for Skill Routing...")
    routing_data = None
    try:
        routing_prompt = f"以下のユーザーの要求に最も適した社内スキルを1つ選んでください。\n選択肢: darts-forecast-skill, opendata-skill, consultant-toolkit, python-safe-coding\n該当しない場合は 'none' としてください。\n\n要求: {prompt}"
        routing_response = await generate_with_retry_async(
            client,
            best_models["Utility"],
            routing_prompt,
            types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SkillRouting,
                temperature=0.1
            )
        )
        total_cost += print_usage(routing_response, best_models["Utility"], routing_prompt, label="Routing")
        routing_data = json.loads(routing_response.text)
        recommended_skill = routing_data.get('recommended_skill')
        print(f"🎯 Recommended Skill: {recommended_skill} (Reason: {routing_data.get('reason')})")

        # --- 6. Agentic Chaining (Auto Run) ---
        if auto_run and recommended_skill and recommended_skill.lower() != "none":
            print(f"🤖 Agentic Chaining: Auto-executing recommended skill '{recommended_skill}'...")
            cmd_prompt = (
                f"ユーザーの要求: {prompt}\n選択されたスキル: {recommended_skill}\n"
                "この要求を満たすために、対象スキルを実行するWindows CLIコマンド（例: python scripts/analyze_company_cli.py ...）を1行で生成してください。\n"
                "Markdownのコードブロック（```）や説明文、改行は一切含めず、コマンド文字列のみを出力してください。\n"
                "特定できない場合は 'UNKNOWN' と出力してください。"
            )
            cmd_response = await generate_with_retry_async(
                client,
                best_models["Utility"],
                cmd_prompt,
                types.GenerateContentConfig(temperature=0.1)
            )
            total_cost += print_usage(cmd_response, best_models["Utility"], cmd_prompt, label="CommandGen")
            cmd = cmd_response.text.strip().replace("```bash", "").replace("```", "").strip()
            if cmd and cmd != "UNKNOWN":
                print(f"🚀 Generated command: {cmd}")
                if not _confirm_command_execution(cmd, auto_confirm=auto_run_yes):
                    print("⚠️ Execution cancelled by user.")
                else:
                    try:
                        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
                        print("✅ Execution Output captured. Injecting into context.")
                        prompt += f"\n\n【自動実行したスキル ({recommended_skill}) の出力結果】\n{result.stdout}"
                    except subprocess.CalledProcessError as e:
                        print(f"❌ Execution Failed. Injecting error into context.\n{e.stderr}")
                        prompt += f"\n\n【自動実行したスキル ({recommended_skill}) のエラー】\n{e.stderr}"
            else:
                print("⚠️ Could not determine a safe command to run.")

    except Exception as e:
         print(f"⚠️ Routing/Agentic Chaining skipped or failed: {e}")

    # --- 複雑度判定によるモデル選択 ---
    complex_keywords: tuple[str, ...] = ("数学", "統計", "最適化", "PSI", "推論", "a^2", "アルゴリズム", "予測")
    is_complex = any(kw in prompt for kw in complex_keywords)

    target_model = best_models["Specialist"] if is_complex else best_models["Primary"]
    thinking_level = "high" if is_complex else "minimal"

    print(f"\n--- 🚀 Main Execution Auto-Selected: {target_model} (Category: {'Specialist' if is_complex else 'Primary'}) ---")

    # --- 7. Context Caching API ---
    cache_name = None
    if cache_file_path and os.path.exists(cache_file_path):
        print(f"📦 Context Caching: Uploading file {cache_file_path}...")
        try:
            uploaded_file = client.files.upload(file=cache_file_path)
            print(f"📦 Context Caching: Creating cache for {target_model}...")
            cache = client.caches.create(
                model=target_model,
                config=types.CreateCacheConfig(
                    contents=[uploaded_file],
                    ttl="300s", # 5 minutes
                )
            )
            cache_name = cache.name
            print("✅ Context Cache created successfully. TTL: 5 mins.")
        except Exception as e:
            print(f"⚠️ Context Caching failed: {e}. Proceeding normally.")

    # --- 3. Structured Output Enforcement & Config Setup ---
    config_args = {"temperature": 1.0}
    if _supports_thinking(target_model):
        config_args["thinking_config"] = types.ThinkingConfig(
            include_thoughts=True,
            thinking_level=thinking_level
        )

    if enforce_json or response_schema:
        config_args["response_mime_type"] = "application/json"
        if response_schema:
            config_args["response_schema"] = response_schema
            print("🧩 Enforcing Pydantic Structured Output Mode.")
        else:
            print("🧩 Enforcing JSON Output Mode.")

    # --- 8. Google Search Grounding ---
    if grounding:
        print("🌍 Enabling Google Search Grounding...")
        config_args["tools"] = [{"google_search": {}}]

    # MCP Tools integration
    mcp_tools = mcp_manager.get_gemini_tools()
    if mcp_tools:
        if "tools" not in config_args:
            config_args["tools"] = []
        config_args["tools"].extend(mcp_tools)

    if cache_name:
        config_args["cached_content"] = cache_name

    config = types.GenerateContentConfig(**config_args)

    # 実行フェーズ (Agentic Loop)
    start_time = time.time()

    conversation_history = [
        types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    ]

    if max_agentic_turns < 1:
        raise ValueError("max_agentic_turns must be >= 1")

    try:
        for turn in range(1, max_agentic_turns + 1):
            response = await generate_with_retry_async(client, target_model, conversation_history, config)

            if response.function_calls:
                total_cost += print_usage(response, target_model, prompt, label=f"Turn {turn}/{max_agentic_turns}")

                # Append model's exact response content to history to preserve thought_signature
                conversation_history.append(response.candidates[0].content)

                # Execute tools
                response_parts = []
                for fc in response.function_calls:
                    result_text = await mcp_manager.call_tool(fc.name, fc.args)
                    response_parts.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": result_text}
                        )
                    )

                # Append tool responses to history
                conversation_history.append(types.Content(role="user", parts=response_parts))
                # Loop back to Gemini for the next step
                continue

            # No function calls, we have the final text answer
            elapsed = time.time() - start_time
            print(f"=== ✨ Response from {target_model} ({elapsed:.2f}s) ===")
            print(response.text)
            total_cost += print_usage(response, target_model, prompt, routing_data, label="Final")
            print(f"💰 [Total Est. Cost for this request] ${total_cost:.6f}")

            return response.text

        # ループが正常にfor文を終えるのは、直前ターンもfunction_callsを返し続けた場合のみ
        # (function_callsが無い最終応答が来た時点で上のブロックが必ずreturnする)。
        # つまりここに到達した時点でモデルはまだ最終テキスト回答を出していない。
        print(f"⚠️ Reached max_agentic_turns={max_agentic_turns} without a final answer.")
        print(f"💰 [Total Est. Cost for this request] ${total_cost:.6f}")
        return None

    except Exception as e:
        # --- フォールバック処理 ---
        fallback_model = best_models["Primary"]
        print(f"⚠️ Error with {target_model} after retries: {e}")
        print(f"--- 🛡️ Falling back to {fallback_model} ---")

        # フォールバックは target_model 失敗直後の再試行なので、thinking_config自体が
        # 失敗原因だった可能性を考慮し、フォールバック時は thinking_config を付与しない
        fallback_config_args = {"temperature": 1.0}
        if enforce_json or response_schema:
            fallback_config_args["response_mime_type"] = "application/json"
            if response_schema:
                fallback_config_args["response_schema"] = response_schema

        if grounding:
            fallback_config_args["tools"] = [{"google_search": {}}]

        fallback_config = types.GenerateContentConfig(**fallback_config_args)

        start_time = time.time()
        try:
            # Fallback uses basic text prompt instead of full history to prevent nested failures
            response = await generate_with_retry_async(client, fallback_model, prompt, fallback_config)
            elapsed = time.time() - start_time
            print(f"=== ✨ Final Answer (Fallback to {fallback_model}) ({elapsed:.2f}s) ===")
            print(response.text)
            total_cost += print_usage(response, fallback_model, prompt, routing_data, label="Fallback")
            print(f"💰 [Total Est. Cost for this request] ${total_cost:.6f}")
            return response.text
        except Exception as fallback_e:
             error_msg = f"❌ Critical Failure. Fallback also failed: {fallback_e}"
             print(error_msg)
             return error_msg

    finally:
        await mcp_manager.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Galaxy Orchestrator (Gemini 3 Native)")
    parser.add_argument("prompt", nargs="*", help="The prompt for the model")
    parser.add_argument("--json", action="store_true", help="Enforce JSON output")
    parser.add_argument("--grounding", action="store_true", help="Enable Google Search Grounding")
    parser.add_argument("--auto-run", action="store_true", help="Auto-execute recommended skills (Agentic Chaining)")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt before executing an --auto-run generated command")
    parser.add_argument("--max-turns", type=int, default=8, help="Max agentic loop turns before aborting (default: 8)")
    parser.add_argument("--cache-file", type=str, help="Path to a file to cache via Context Caching API")

    args = parser.parse_args()

    input_prompt = " ".join(args.prompt)
    if not input_prompt:
        print("Usage: python orchestrator.py [--json] [--grounding] [--auto-run] [--yes] [--max-turns N] [--cache-file <path>] 'your prompt here'")
        sys.exit(1)

    asyncio.run(
        run_orchestrator(
            prompt=input_prompt,
            enforce_json=args.json,
            grounding=args.grounding,
            auto_run=args.auto_run,
            auto_run_yes=args.yes,
            cache_file_path=args.cache_file,
            max_agentic_turns=args.max_turns
        )
    )
