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

import os
import sys
import urllib.request
from pathlib import Path

from google import genai
from google.genai import types

ENV_PATH = Path(os.environ.get("GEMINI_SKILL_ENV_PATH", r"C:\Users\iidam\gemini\.env"))


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


def search(query: str, model: str = "gemini-3.6-flash", no_resolve: bool = False) -> None:
    load_env(ENV_PATH)

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"

    if api_key:
        client = genai.Client(api_key=api_key, vertexai=False)
    elif use_vertex:
        client = genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    else:
        print("ERROR: GEMINI_API_KEY / GOOGLE_API_KEY か Vertex AI設定が見つかりません。", file=sys.stderr)
        sys.exit(1)

    response = client.models.generate_content(
        model=model,
        contents=query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    print(response.text)

    grounding = response.candidates[0].grounding_metadata if response.candidates else None
    chunks = getattr(grounding, "grounding_chunks", None) if grounding else None
    if chunks:
        print("\n--- 出典 ---")
        for i, chunk in enumerate(chunks, 1):
            web = getattr(chunk, "web", None)
            if not web:
                continue
            resolved = resolve_redirect(web.uri) if not no_resolve else None
            if resolved:
                print(f"[{i}] {web.title} - {resolved}")
            else:
                suffix = " (解決失敗、リダイレクトURLのまま)" if not no_resolve else ""
                print(f"[{i}] {web.title} - {web.uri}{suffix}")


if __name__ == "__main__":
    args = sys.argv[1:]
    no_resolve = "--no-resolve" in args
    if no_resolve:
        args.remove("--no-resolve")
    if not args:
        print("使い方: python gemini_websearch.py \"検索クエリ\" [--no-resolve]", file=sys.stderr)
        sys.exit(1)
    search(" ".join(args), no_resolve=no_resolve)
