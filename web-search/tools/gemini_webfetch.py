"""
Gemini API (URL context tool) を使ったWebFetchツール。

Claude CodeのWebFetchツールの代替。指定URLの内容をGemini経由で取得・要約する。
証明書エラー等でClaude側のWebFetchが失敗するサイトでも、Google側の取得経路を
使うため成功することがある(ただし取得元は同じインターネット上のサイトであり、
Geminiが実際にライブ取得したかキャッシュを使ったかはurl_retrieval_statusでしか
判別できない点に注意)。

使い方:
    cd claude-gemini-skills/web-search && uv run python tools/gemini_webfetch.py <URL> ["追加の指示"]

追加の指示を省略した場合は「ページの内容を詳しく要約して」を使う。

APIキー/Vertex AI設定は既定で C:/Users/iidam/gemini/.env から読み込む
(環境変数 GEMINI_SKILL_ENV_PATH で上書き可能)。

出力:
    Geminiの回答本文と、URL取得ステータス(成功/失敗)。
"""

import os
import sys
from pathlib import Path

from google import genai
from google.genai import types

ENV_PATH = Path(os.environ.get("GEMINI_SKILL_ENV_PATH", r"C:\Users\iidam\gemini\.env"))
DEFAULT_INSTRUCTION = "このページの内容を詳しく要約して"


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


def make_client() -> genai.Client:
    load_env(ENV_PATH)

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"

    if api_key:
        return genai.Client(api_key=api_key, vertexai=False)
    if use_vertex:
        return genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    print("ERROR: GEMINI_API_KEY / GOOGLE_API_KEY か Vertex AI設定が見つかりません。", file=sys.stderr)
    sys.exit(1)


def fetch_raw(url: str, instruction: str = DEFAULT_INSTRUCTION, model: str = "gemini-3.6-flash", client: genai.Client | None = None) -> dict:
    """URLを取得しGeminiの回答本文・取得ステータスを辞書で返す（他スクリプトからの再利用向け）。"""
    client = client or make_client()

    response = client.models.generate_content(
        model=model,
        contents=f"{instruction}: {url}",
        config=types.GenerateContentConfig(
            tools=[types.Tool(url_context=types.UrlContext())],
        ),
    )

    metadata = response.candidates[0].url_context_metadata if response.candidates else None
    url_metas = getattr(metadata, "url_metadata", None) if metadata else None
    statuses = []
    if url_metas:
        for m in url_metas:
            statuses.append({"status": m.url_retrieval_status.name, "retrieved_url": m.retrieved_url})

    return {"text": response.text, "statuses": statuses}


def fetch(url: str, instruction: str = DEFAULT_INSTRUCTION, model: str = "gemini-3.6-flash") -> None:
    result = fetch_raw(url, instruction, model)

    print(result["text"])

    if result["statuses"]:
        print("\n--- 取得ステータス ---")
        for s in result["statuses"]:
            print(f"{s['status']}  {s['retrieved_url']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('使い方: python gemini_webfetch.py <URL> ["追加の指示"]', file=sys.stderr)
        sys.exit(1)
    target_url = sys.argv[1]
    extra_instruction = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else DEFAULT_INSTRUCTION
    fetch(target_url, extra_instruction)
