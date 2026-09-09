"""
Gemini API (Google Search grounding) を使ったWeb検索ツール。

Claude CodeのWebSearchツールの代替。GEMINI_API_KEY / GOOGLE_API_KEYが必要。

使い方:
    cd claude-gemini-skills/web-search && uv run python tools/gemini_websearch.py "検索したい質問や単語"

APIキー/Vertex AI設定は既定で C:/Users/iidam/gemini/.env から読み込む
(環境変数 GEMINI_SKILL_ENV_PATH で上書き可能。GOOGLE_GENAI_USE_VERTEXAI=true の場合はAPIキー不要、ADC認証を使用)。

出力:
    Geminiが生成した回答本文と、根拠にした情報源URL一覧(grounding citations)。
"""

import argparse
from datetime import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).parent))
from gemini_webfetch import _truncate, check_claim_raw, make_client, resolve_redirect  # noqa: E402

ENV_PATH = Path(os.environ.get("GEMINI_SKILL_ENV_PATH", r"C:\Users\iidam\gemini\.env"))

REFUTE_TEMPLATE = (
    "次の主張について、これを否定・反証する情報や、矛盾する独立の情報源がないか重点的に調べて報告して。"
    "肯定的な情報がある場合も併記してよいが、まず反証の可能性を優先して探すこと。主張: {claim}"
)

MAX_VERIFY_WORKERS = 4
MAX_RESOLVE_WORKERS = 8


def get_system_instruction() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return (
        f"あなたは厳格な事実調査アシスタントです。現在の基準日は {today} です。\n"
        "【絶対規律】\n"
        "1. 提供されたGoogle検索結果（Grounding情報）に明確に記載されている事実・数値のみを回答してください。\n"
        "2. 検索結果に書かれていない数値を、あなたの事前学習知識や推測で補完・創作することは厳禁です。\n"
        "3. 検索結果に記載がない場合は『検索結果に記載なし』と正直に回答してください。\n"
        "4. 金額、増減率、年度（3月期/12月期等）、企業名は検索結果の表記を正確に反映してください。"
    )


def audit_grounding(text: str, grounding_supports: list, sources: list) -> dict:
    """テキストとgrounding_supportsを突合し、文単位の裏付け状態を監査する。"""
    segments = []
    if not grounding_supports:
        return {
            "verified_segments": [],
            "ungrounded_snippets": [],
            "is_fully_grounded": False,
        }

    for s in grounding_supports:
        seg = getattr(s, "segment", None)
        if not seg or not getattr(seg, "text", None):
            continue
        indices = getattr(s, "grounding_chunk_indices", []) or []
        ref_sources = [
            {"index": idx + 1, "title": sources[idx]["title"], "url": sources[idx]["url"]}
            for idx in indices if idx < len(sources)
        ]
        segments.append({
            "text": seg.text.strip(),
            "has_grounding": bool(indices),
            "sources": ref_sources,
        })

    # 未裏付け文（Un-grounded text）の検出
    ungrounded_snippets = []
    lines = [
        line.strip() for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("---")
    ]
    boilerplate_patterns = ("以下のとおり", "以下の通り", "下記のとおり", "下記の通り", "まとめました", "紹介します", "まとめは以下")
    for line in lines:
        if len(line) < 15:  # 短い見出しや箇条書きマーカーのみは除外
            continue
        if any(bp in line for bp in boilerplate_patterns):
            continue
        is_covered = any(line in s["text"] or s["text"] in line for s in segments if s["has_grounding"])
        if not is_covered:
            ungrounded_snippets.append(line)

    return {
        "verified_segments": segments,
        "ungrounded_snippets": ungrounded_snippets,
        "is_fully_grounded": len(ungrounded_snippets) == 0,
    }


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def search_raw(
    query: str,
    model: str = "gemini-3.8-flash",
    no_resolve: bool = False,
    client: genai.Client | None = None,
    no_audit: bool = False,
    thinking_budget: int | None = None,
) -> dict:
    """検索を実行し、回答本文・出典リスト・検索クエリ・裏付け監査を辞書で返す。"""
    client = client or make_client()

    config_kwargs = {
        "tools": [types.Tool(google_search=types.GoogleSearch())],
        "system_instruction": get_system_instruction(),
        "temperature": 0.0,
    }
    if thinking_budget is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)

    response = client.models.generate_content(
        model=model,
        contents=query,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    sources = []
    search_queries = []
    grounding = response.candidates[0].grounding_metadata if response.candidates else None
    chunks = getattr(grounding, "grounding_chunks", None) if grounding else None
    if grounding:
        search_queries = getattr(grounding, "web_search_queries", []) or []

    if chunks:
        # 重複URIを排除して並列で実URL解決を行う
        resolved_map: dict[str, str | None] = {}
        if not no_resolve:
            unique_uris = {
                chunk.web.uri for chunk in chunks
                if getattr(chunk, "web", None) and getattr(chunk.web, "uri", None)
            }
            if unique_uris:
                with ThreadPoolExecutor(max_workers=min(MAX_RESOLVE_WORKERS, len(unique_uris))) as pool:
                    future_to_uri = {pool.submit(resolve_redirect, uri): uri for uri in unique_uris}
                    for fut in future_to_uri:
                        uri = future_to_uri[fut]
                        try:
                            resolved_map[uri] = fut.result()
                        except Exception:
                            resolved_map[uri] = None

        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if not web:
                continue
            resolved = resolved_map.get(web.uri) if not no_resolve else None
            sources.append({
                "title": web.title,
                "url": resolved or web.uri,
                "resolved": bool(resolved),
            })

    audit_result = None
    if not no_audit and grounding:
        supports = getattr(grounding, "grounding_supports", []) or []
        audit_result = audit_grounding(response.text, supports, sources)

    return {
        "text": response.text,
        "sources": sources,
        "search_queries": search_queries,
        "supports_audit": audit_result,
    }


def verify_claim(text: str, sources: list, client: genai.Client, model: str = "gemini-3.8-flash") -> list:
    """回答本文の主張を項目単位に分解し、各出典ページで裏付けられるかを並列にクロスチェックする。

    出典ごとのcheck_claim_raw呼び出しは互いに独立しているため、
    ThreadPoolExecutorで並列実行し待ち時間を「出典数×1回」から「1回」に短縮する。
    """
    claim = text[:500]

    def _check_one(src: dict) -> dict:
        result = check_claim_raw(src["url"], claim, model=model, client=client)
        return {
            "title": src["title"],
            "url": src["url"],
            "items": result["items"],
            "fetch_status": result["statuses"],
        }

    with ThreadPoolExecutor(max_workers=min(MAX_VERIFY_WORKERS, len(sources))) as pool:
        return list(pool.map(_check_one, sources))


def search(
    query: str,
    model: str = "gemini-3.8-flash",
    no_resolve: bool = False,
    as_json: bool = False,
    do_verify: bool = False,
    do_refute: bool = False,
    max_chars: int | None = None,
    no_audit: bool = False,
    thinking_budget: int | None = None,
) -> None:
    load_env(ENV_PATH)
    client = make_client()

    if do_refute:
        query = REFUTE_TEMPLATE.format(claim=query)

    result = search_raw(
        query,
        model=model,
        no_resolve=no_resolve,
        client=client,
        no_audit=no_audit,
        thinking_budget=thinking_budget,
    )

    checks = None
    if do_verify and result["sources"]:
        checks = verify_claim(result["text"], result["sources"], client, model=model)

    if as_json:
        payload = {
            "text": _truncate(result["text"], max_chars),
            "sources": result["sources"],
            "search_queries": result["search_queries"],
        }
        if result["supports_audit"] is not None:
            payload["supports_audit"] = result["supports_audit"]
        if checks is not None:
            payload["claim_checks"] = checks
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(_truncate(result["text"], max_chars))

    if result["search_queries"]:
        print("\n--- 検索クエリ (web_search_queries) ---")
        for q in result["search_queries"]:
            print(f"- {q}")

    if result["sources"]:
        print("\n--- 出典 ---")
        for i, src in enumerate(result["sources"], 1):
            suffix = "" if src["resolved"] or no_resolve else " (解決失敗、リダイレクトURLのまま)"
            print(f"[{i}] {src['title']} - {src['url']}{suffix}")

    audit = result.get("supports_audit")
    if audit is not None:
        print("\n--- 文単位の裏付け監査 (Grounding Audit) ---")
        if audit["is_fully_grounded"]:
            print("Status: OK (すべての主要文章がWeb出典に基づいています)")
        else:
            print("Status: WARNING (Web出典で裏付けられていない文が含まれています)")

        if audit["ungrounded_snippets"]:
            print("\n⚠️ 【Web出典の裏付けなし（モデル推測・事前知識の可能性）】:")
            for s in audit["ungrounded_snippets"]:
                print(f"  * {s}")

    if checks is not None:
        print("\n--- 出典の裏付けチェック（--verify-claim、主張を項目単位に分解して判定） ---")
        for i, c in enumerate(checks, 1):
            print(f"[{i}] {c['title']} - {c['url']}")
            for item in c["items"]:
                print(f"    {item['verdict']}  {item['claim']}")
                print(f"      {item['detail']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gemini_websearch.py",
        description="Gemini API (Google Search grounding) を使ったWeb検索。回答本文の主張の裏取り・反証も行える。",
    )
    parser.add_argument("query", nargs="+", help="検索クエリ")
    parser.add_argument("--no-resolve", action="store_true", help="出典URLのリダイレクト解決を無効化する")
    parser.add_argument("--json", action="store_true", help="結果をJSONで出力する")
    parser.add_argument(
        "--model", default="gemini-3.8-flash",
        help="使用するGeminiモデル（既定: gemini-3.8-flash。例: gemini-3.1-pro-preview）",
    )
    parser.add_argument(
        "--verify-claim", action="store_true",
        help="回答本文の主張を項目単位に分解し、各出典ページで裏付けられるか並列でクロスチェックする",
    )
    parser.add_argument(
        "--refute", action="store_true",
        help="クエリを反証志向のプロンプトに変換してから検索する（否定・矛盾情報を優先的に探す）",
    )
    parser.add_argument(
        "--max-chars", type=int, default=None,
        help="回答本文をこの文字数で打ち切る（呼び出し元＝Claude側のコンテキスト消費を抑えたい時に指定。出典一覧・--verify-claim結果には影響しない）",
    )
    parser.add_argument(
        "--no-audit", action="store_true",
        help="文単位の裏付け監査（grounding_supports突合）を無効化する（既定は有効）",
    )
    parser.add_argument(
        "--thinking", action="store_true",
        help="思考プロセス（Thinking）を有効化して論理・数理の突合精度を高める（既定バジェット 1024）",
    )
    parser.add_argument(
        "--thinking-budget", type=int, default=None,
        help="思考プロセス（Thinking）のトークンバジェットを指定する（例: 2048）",
    )
    args = parser.parse_args()

    budget = args.thinking_budget if args.thinking_budget is not None else (1024 if args.thinking else None)

    search(
        " ".join(args.query),
        model=args.model,
        no_resolve=args.no_resolve,
        as_json=args.json,
        do_verify=args.verify_claim,
        do_refute=args.refute,
        max_chars=args.max_chars,
        no_audit=args.no_audit,
        thinking_budget=budget,
    )


if __name__ == "__main__":
    main()

