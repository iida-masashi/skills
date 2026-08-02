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

import json
import os
import sys
import urllib.request
from pathlib import Path

from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).parent))
from gemini_webfetch import fetch_raw, make_client  # noqa: E402

ENV_PATH = Path(os.environ.get("GEMINI_SKILL_ENV_PATH", r"C:\Users\iidam\gemini\.env"))

REFUTE_TEMPLATE = (
    "次の主張について、これを否定・反証する情報や、矛盾する独立の情報源がないか重点的に調べて報告して。"
    "肯定的な情報がある場合も併記してよいが、まず反証の可能性を優先して探すこと。主張: {claim}"
)


def resolve_redirect(url: str, timeout: float = 10.0) -> str | None:
    """grounding-api-redirect URLを実URLに解決する。失敗時はNone。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.geturl()
    except Exception:
        return None


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


def search_raw(query: str, model: str = "gemini-3.6-flash", no_resolve: bool = False, client: genai.Client | None = None) -> dict:
    """検索を実行し、回答本文と出典リストを辞書で返す（他スクリプトからの再利用・--json向け）。"""
    client = client or make_client()

    response = client.models.generate_content(
        model=model,
        contents=query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    sources = []
    grounding = response.candidates[0].grounding_metadata if response.candidates else None
    chunks = getattr(grounding, "grounding_chunks", None) if grounding else None
    if chunks:
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if not web:
                continue
            resolved = resolve_redirect(web.uri) if not no_resolve else None
            sources.append({
                "title": web.title,
                "url": resolved or web.uri,
                "resolved": bool(resolved),
            })

    return {"text": response.text, "sources": sources}


def verify_claim(text: str, sources: list, client: genai.Client) -> list:
    """回答本文の主張が各出典ページに実在するかを、gemini_webfetchで個別にクロスチェックする。"""
    checks = []
    instruction = (
        "次の主張がこのページの内容に実在するか確認して。"
        "ページ内に主張を裏付ける記述があれば「裏付けあり」、なければ「裏付けなし」、"
        "判断できなければ「不明」を先頭に一言で示してから、根拠を簡潔に述べて。"
        f"主張: {text[:500]}"
    )
    for src in sources:
        result = fetch_raw(src["url"], instruction=instruction, client=client)
        verdict_text = result["text"].strip()
        if verdict_text.startswith("裏付けあり"):
            verdict = "裏付けあり"
        elif verdict_text.startswith("裏付けなし"):
            verdict = "裏付けなし"
        else:
            verdict = "不明"
        checks.append({
            "title": src["title"],
            "url": src["url"],
            "verdict": verdict,
            "detail": verdict_text,
            "fetch_status": result["statuses"],
        })
    return checks


def search(query: str, model: str = "gemini-3.6-flash", no_resolve: bool = False,
           as_json: bool = False, do_verify: bool = False, do_refute: bool = False) -> None:
    load_env(ENV_PATH)
    client = make_client()

    if do_refute:
        query = REFUTE_TEMPLATE.format(claim=query)

    result = search_raw(query, model=model, no_resolve=no_resolve, client=client)

    checks = None
    if do_verify and result["sources"]:
        checks = verify_claim(result["text"], result["sources"], client)

    if as_json:
        payload = {"text": result["text"], "sources": result["sources"]}
        if checks is not None:
            payload["claim_checks"] = checks
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(result["text"])

    if result["sources"]:
        print("\n--- 出典 ---")
        for i, src in enumerate(result["sources"], 1):
            suffix = "" if src["resolved"] or no_resolve else " (解決失敗、リダイレクトURLのまま)"
            print(f"[{i}] {src['title']} - {src['url']}{suffix}")

    if checks is not None:
        print("\n--- 出典の裏付けチェック（--verify-claim） ---")
        for i, c in enumerate(checks, 1):
            print(f"[{i}] {c['verdict']}  {c['title']} - {c['url']}")
            print(f"    {c['detail'][:200]}")


if __name__ == "__main__":
    args = sys.argv[1:]
    no_resolve = "--no-resolve" in args
    if no_resolve:
        args.remove("--no-resolve")
    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    do_verify = "--verify-claim" in args
    if do_verify:
        args.remove("--verify-claim")
    do_refute = "--refute" in args
    if do_refute:
        args.remove("--refute")
    if not args:
        print(
            "使い方: python gemini_websearch.py \"検索クエリ\" [--no-resolve] [--json] [--verify-claim] [--refute]",
            file=sys.stderr,
        )
        sys.exit(1)
    search(" ".join(args), no_resolve=no_resolve, as_json=as_json, do_verify=do_verify, do_refute=do_refute)
