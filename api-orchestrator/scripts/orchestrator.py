import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from dotenv import load_dotenv
from mcp_manager import MCPManager
from providers import GeminiProvider, GrokProvider, _supports_thinking  # noqa: F401  (_supports_thinking はテストから参照)
from pydantic import BaseModel, Field
from scout import GEMINI_DEFAULTS, get_best_available_models, get_best_grok_models

PROVIDERS = ("gemini", "grok")


# --- Pydantic Schemas for Structured Output ---
class SkillRouting(BaseModel):
    recommended_skill: str = Field(description="The most appropriate skill for the task (e.g., darts-forecast-skill, opendata-skill, consultant-toolkit, python-safe-coding, or none)")
    reason: str = Field(description="Reason for recommending this skill")


# --- 1. Token & Cost Tracker Constants ---
# Gemini の料金は https://ai.google.dev/gemini-api/docs/pricing (有料枠Standard, テキスト, 200kトークン以下) の
# 1Mトークン単価(USD)。2026-10-04 に WebFetch で2回取得し値が一致したもの (生HTMLでの確認は未実施)。
# 3.6/3.7/3.8-flash は 2026-12-31 までの価格で、2027-01-01 から in=1.50/out=7.50 に倍増する。
# Grok の料金はハードコードせず、起動時に xAI の /v1/language-models から取得して GROK_COST_PER_1M に入れる。
# calculate_cost はキーを「文字列が長い順」に評価し、最も具体的な一致を優先する
# ("gemini-3.5-flash-lite" が "gemini-3.5-flash" のレートで計算されないようにするため)
COST_PER_1M_TOKENS = {
    "gemini-3.1-pro": {"in": 2.00, "out": 12.00},
    "gemini-3.8-flash": {"in": 0.75, "out": 3.75},
    "gemini-3.7-flash": {"in": 0.75, "out": 3.75},
    "gemini-3.6-flash": {"in": 0.75, "out": 3.75},
    "gemini-3.5-flash": {"in": 1.50, "out": 9.00},
    "gemini-3.5-flash-lite": {"in": 0.30, "out": 2.50},
    "gemini-3.1-flash-lite": {"in": 0.25, "out": 1.50},
    "gemini-3-flash": {"in": 0.50, "out": 3.00},
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50},
    "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40},
}
GROK_COST_PER_1M: dict[str, dict[str, float]] = {}


def calculate_cost(model_name: str, prompt_tokens: int, candidates_tokens: int) -> float:
    """トークン数から概算コスト（USD）を計算する"""
    rate = GROK_COST_PER_1M.get(model_name)
    if rate is None:
        for k in sorted(COST_PER_1M_TOKENS, key=len, reverse=True):
            if k in model_name:
                rate = COST_PER_1M_TOKENS[k]
                break
    if rate is None:
        rate = {"in": 0.10, "out": 0.40}

    return (prompt_tokens / 1_000_000) * rate["in"] + (candidates_tokens / 1_000_000) * rate["out"]


def log_usage(model_name: str, prompt: str, response_text: str, usage: Any, cost: float, routing: dict | None = None) -> None:
    """使用状況を JSONL ログファイルに記録する"""
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


def _extract_usage(response: Any, model_name: str) -> tuple[Any, str]:
    """レスポンスから (Gemini形式のusage, 本文) を取り出す。
    Grok (Responses API) の usage は input_tokens/output_tokens なので Gemini 形式に揃える。
    Gemini の思考トークンは candidates_token_count に含まれないが出力単価で課金されるため加算する"""
    if model_name.startswith("grok"):
        u = getattr(response, "usage", None)
        usage = SimpleNamespace(
            prompt_token_count=u.input_tokens,
            candidates_token_count=u.output_tokens,
            total_token_count=u.total_tokens,
        ) if u else None
        return usage, getattr(response, "output_text", "") or ""

    meta = getattr(response, "usage_metadata", None)
    usage = None
    if meta:
        thoughts = getattr(meta, "thoughts_token_count", None)
        usage = SimpleNamespace(
            prompt_token_count=meta.prompt_token_count or 0,
            candidates_token_count=(meta.candidates_token_count or 0) + (thoughts if isinstance(thoughts, int) else 0),
            total_token_count=meta.total_token_count or 0,
        )
    return usage, getattr(response, "text", "") or ""


def print_usage(response: Any, model_name: str, prompt: str, routing: dict | None = None, label: str = "") -> float:
    """レスポンスからトークン使用量とコストを抽出し出力・記録する。
    label はどの呼び出し(圧縮/ルーティング/メイン等)かを示す接頭辞。"""
    prefix = f"[{label}] " if label else ""
    usage, response_text = _extract_usage(response, model_name)
    if not usage:
        print(f"📊 {prefix}[Token & Cost Tracker] Usage metadata not available.")
        return 0.0
    cost = calculate_cost(model_name, usage.prompt_token_count, usage.candidates_token_count)
    print(f"📊 {prefix}[Token & Cost Tracker] {model_name} | In: {usage.prompt_token_count} | Out: {usage.candidates_token_count} | Total: {usage.total_token_count} | Est. Cost: ${cost:.6f}")
    log_usage(model_name, prompt, response_text, usage, cost, routing)
    return cost


def build_provider(name: str) -> GeminiProvider | GrokProvider | None:
    """APIキーがあればプロバイダを作り、利用可能なモデルを偵察してティアを決める。キーが無ければNone"""
    if name == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None
        return GeminiProvider(api_key, get_best_available_models() or dict(GEMINI_DEFAULTS))

    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        return None
    tiers, pricing = get_best_grok_models() or ({}, {})
    GROK_COST_PER_1M.update(pricing)
    return GrokProvider(api_key, tiers)


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
    provider: str = "gemini",
    enforce_json: bool = False,
    response_schema: type[BaseModel] | None = None,
    grounding: bool = False,
    auto_run: bool = False,
    auto_run_yes: bool = False,
    cache_file_path: str | None = None,
    max_agentic_turns: int = 8
) -> str | None:
    """
    API Orchestrator (Gemini / Grok): MCP 連携による自律型エージェントループ対応版。
    provider で選んだ側で実行し、全滅した場合はもう一方のプロバイダの Primary に切り替える
    """
    load_dotenv()
    if max_agentic_turns < 1:
        raise ValueError("max_agentic_turns must be >= 1")

    llm = build_provider(provider)
    if llm is None:
        key_name = "GOOGLE_API_KEY (or GEMINI_API_KEY)" if provider == "gemini" else "XAI_API_KEY"
        print(f"❌ Error: {key_name} is missing in .env")
        sys.exit(1)
    best_models = llm.models
    print(f"🛰️ Provider: {llm.name} | Specialist={best_models['Specialist']} Primary={best_models['Primary']} Utility={best_models['Utility']}")

    # このリクエスト全体(圧縮/ルーティング/コマンド生成/メイン/ループ中間ターンを含む)で
    # 発生した推定コストの合計。track を呼ぶたびに加算する
    total_cost = 0.0

    def track(response: Any, model: str, track_prompt: str, label: str, routing: dict | None = None) -> None:
        nonlocal total_cost
        total_cost += print_usage(response, model, track_prompt, routing, label=label)

    # Context Caching は Gemini 専用。Grok ではファイル本文をプロンプトに直接埋め込む
    # (xAI 側でプロンプトの自動キャッシュが効く)
    if cache_file_path and os.path.exists(cache_file_path) and not llm.supports_cache:
        print(f"📎 {llm.name} has no Context Caching API: inlining {cache_file_path} into the prompt.")
        with open(cache_file_path, encoding="utf-8", errors="replace") as f:
            prompt = f"【添付ファイル: {os.path.basename(cache_file_path)}】\n{f.read()}\n\n【要求】\n{prompt}"
        cache_file_path = None

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
            compression_response = await llm.quick(best_models["Utility"], compression_prompt)
            track(compression_response, best_models["Utility"], compression_prompt, "Compression")
            # 要約されたコンテキストと、失われてはいけない直近のプロンプトを結合。
            # 実際の指示は多くの場合プロンプト末尾に来るため、先頭だけでなく末尾も保持する
            head_len, tail_len = 500, 1000
            if len(prompt) > head_len + tail_len:
                original_excerpt = f"{prompt[:head_len]}\n...[MIDDLE TRUNCATED]...\n{prompt[-tail_len:]}"
            else:
                original_excerpt = prompt
            prompt = f"【要約されたコンテキスト】\n{llm.text_of(compression_response)}\n\n【元の要求（抜粋）】\n{original_excerpt}"
            print("✅ Context dynamically compressed to save tokens.")
        except Exception as e:
            print(f"⚠️ Compression failed, proceeding with original prompt: {e}")

    # --- 5. Skill Dispatcher (Routing) ---
    print("🧭 Analyzing intent for Skill Routing...")
    routing_data = None
    try:
        routing_prompt = f"以下のユーザーの要求に最も適した社内スキルを1つ選んでください。\n選択肢: darts-forecast-skill, opendata-skill, consultant-toolkit, python-safe-coding\n該当しない場合は 'none' としてください。\n\n要求: {prompt}"
        routing_response = await llm.quick(best_models["Utility"], routing_prompt, response_schema=SkillRouting)
        track(routing_response, best_models["Utility"], routing_prompt, "Routing")
        routing_data = json.loads(llm.text_of(routing_response))
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
            cmd_response = await llm.quick(best_models["Utility"], cmd_prompt)
            track(cmd_response, best_models["Utility"], cmd_prompt, "CommandGen")
            cmd = llm.text_of(cmd_response).strip().replace("```bash", "").replace("```", "").strip()
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
    print(f"\n--- 🚀 Main Execution Auto-Selected: {target_model} (Category: {'Specialist' if is_complex else 'Primary'}) ---")
    if enforce_json or response_schema:
        print("🧩 Enforcing Pydantic Structured Output Mode." if response_schema else "🧩 Enforcing JSON Output Mode.")
    if grounding:
        print("🌍 Enabling Web Search Grounding...")

    # --- 7. Context Caching API (Gemini) ---
    cache_name = None
    if cache_file_path and os.path.exists(cache_file_path):
        print(f"📦 Context Caching: Uploading {cache_file_path} and creating cache for {target_model}...")
        try:
            cache_name = llm.create_cache(target_model, cache_file_path)
            print("✅ Context Cache created successfully. TTL: 5 mins.")
        except Exception as e:
            print(f"⚠️ Context Caching failed: {e}. Proceeding normally.")

    output_opts = {"enforce_json": enforce_json, "response_schema": response_schema, "grounding": grounding}

    def finish(provider_obj: Any, response: Any, model: str, label: str, start_time: float) -> str:
        """最終レスポンスのコストを記録して本文を返す。本文が空なら例外にして次のフォールバックへ進める
        (例: Gemini でWeb検索とJSONモードを併用すると、検索を繰り返した末に本文なしで終わることがある)"""
        track(response, model, prompt, label, routing_data)
        text = provider_obj.text_of(response)
        if not text.strip():
            raise RuntimeError(f"{model} returned an empty answer")
        print(f"=== ✨ {label} from {model} ({time.time() - start_time:.2f}s) ===")
        print(text)
        print(f"💰 [Total Est. Cost for this request] ${total_cost:.6f}")
        return text

    try:
        # 実行フェーズ (Agentic Loop)
        try:
            start_time = time.time()
            response = await llm.agent(
                target_model, prompt, complex_task=is_complex, mcp_manager=mcp_manager,
                max_turns=max_agentic_turns, track=track, cache_name=cache_name, **output_opts,
            )
            if response is None:
                # 直前ターンまでツール呼び出しが続き、最終テキスト回答に到達しなかった。
                # 失敗として扱い、ツールを使わない単発プロンプトのフォールバックへ進む
                raise RuntimeError(f"Reached max_agentic_turns={max_agentic_turns} without a final answer")
            return finish(llm, response, target_model, "Final", start_time)
        except Exception as e:
            print(f"⚠️ Error with {target_model} after retries: {e}")

        # --- フォールバック1: 同じプロバイダの Primary (履歴を使わない単発プロンプト) ---
        fallback_model = best_models["Primary"]
        print(f"--- 🛡️ Falling back to {fallback_model} ---")
        try:
            start_time = time.time()
            response = await llm.simple(fallback_model, prompt, **output_opts)
            return finish(llm, response, fallback_model, "Fallback", start_time)
        except Exception as e:
            print(f"⚠️ Fallback {fallback_model} also failed: {e}")

        # --- フォールバック2: もう一方のプロバイダの Primary ---
        other_name = next(p for p in PROVIDERS if p != llm.name)
        other = build_provider(other_name)
        if other is None:
            error_msg = f"❌ Critical Failure. No API key for cross-provider fallback ({other_name})."
            print(error_msg)
            return error_msg
        other_model = other.models["Primary"]
        print(f"--- 🛡️ Falling back to other provider: {other_name} / {other_model} ---")
        try:
            start_time = time.time()
            response = await other.simple(other_model, prompt, **output_opts)
            return finish(other, response, other_model, "Cross-provider Fallback", start_time)
        except Exception as e:
            error_msg = f"❌ Critical Failure. Cross-provider fallback also failed: {e}"
            print(error_msg)
            return error_msg

    finally:
        await mcp_manager.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="API Orchestrator (Gemini / Grok)")
    parser.add_argument("prompt", nargs="*", help="The prompt for the model")
    parser.add_argument("--provider", choices=PROVIDERS, default="gemini", help="LLM provider (default: gemini). Falls back to the other provider on total failure")
    parser.add_argument("--json", action="store_true", help="Enforce JSON output")
    parser.add_argument("--grounding", action="store_true", help="Enable web search grounding (Gemini: google_search / Grok: web_search)")
    parser.add_argument("--auto-run", action="store_true", help="Auto-execute recommended skills (Agentic Chaining)")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt before executing an --auto-run generated command")
    parser.add_argument("--max-turns", type=int, default=8, help="Max agentic loop turns before aborting (default: 8)")
    parser.add_argument("--cache-file", type=str, help="Path to a file to cache via Context Caching API (Gemini) / inline into the prompt (Grok)")

    args = parser.parse_args()

    input_prompt = " ".join(args.prompt)
    if not input_prompt:
        print("Usage: python orchestrator.py [--provider gemini|grok] [--json] [--grounding] [--auto-run] [--yes] [--max-turns N] [--cache-file <path>] 'your prompt here'")
        sys.exit(1)

    asyncio.run(
        run_orchestrator(
            prompt=input_prompt,
            provider=args.provider,
            enforce_json=args.json,
            grounding=args.grounding,
            auto_run=args.auto_run,
            auto_run_yes=args.yes,
            cache_file_path=args.cache_file,
            max_agentic_turns=args.max_turns
        )
    )
