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

import argparse
import json
import os
import re
import sys
from pathlib import Path

from google import genai
from google.genai import types

ENV_PATH = Path(os.environ.get("GEMINI_SKILL_ENV_PATH", r"C:\Users\iidam\gemini\.env"))
DEFAULT_INSTRUCTION = "このページの内容を詳しく要約して"

CHECK_INSTRUCTION_TEMPLATE = """次の主張を、否定できない事実の最小単位ごとに箇条書きに分解し、
このページの内容が各項目を裏付けるか判定して。判定は「裏付けあり」「裏付けなし」「不明」の
いずれか一言。厳密に次のJSON形式のみで出力すること（前後に説明文・コードフェンスは付けない）。

{{"items": [{{"claim": "分解した項目の文", "verdict": "裏付けあり|裏付けなし|不明", "detail": "根拠を1文で"}}]}}

主張: {claim}"""


def _parse_check_json(text: str) -> list[dict] | None:
    """--checkの応答からJSON部分を抽出してパースする。失敗時はNone。"""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed.get("items")
    except (json.JSONDecodeError, AttributeError):
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


def check_claim_raw(url: str, claim: str, model: str = "gemini-3.6-flash", client: genai.Client | None = None) -> dict:
    """主張を項目単位に分解し、URLの内容が各項目を裏付けるか判定する（他スクリプトからの再利用向け）。"""
    instruction = CHECK_INSTRUCTION_TEMPLATE.format(claim=claim)
    result = fetch_raw(url, instruction=instruction, model=model, client=client)
    items = _parse_check_json(result["text"])
    if items is None:
        # JSON化に失敗した場合はraw textを1項目として扱う（完全なフォールバック）
        items = [{"claim": claim, "verdict": "不明", "detail": result["text"][:300]}]
    return {"url": url, "items": items, "statuses": result["statuses"]}


def fetch(url: str, instruction: str = DEFAULT_INSTRUCTION, model: str = "gemini-3.6-flash") -> None:
    result = fetch_raw(url, instruction, model)

    print(result["text"])

    if result["statuses"]:
        print("\n--- 取得ステータス ---")
        for s in result["statuses"]:
            print(f"{s['status']}  {s['retrieved_url']}")


def check(url: str, claim: str, model: str = "gemini-3.6-flash", as_json: bool = False) -> None:
    result = check_claim_raw(url, claim, model=model)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"URL: {url}")
    print(f"主張: {claim}\n")
    for i, item in enumerate(result["items"], 1):
        print(f"[{i}] {item['verdict']}  {item['claim']}")
        print(f"    {item['detail']}")

    if result["statuses"]:
        print("\n--- 取得ステータス ---")
        for s in result["statuses"]:
            print(f"{s['status']}  {s['retrieved_url']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gemini_webfetch.py",
        description="指定URLの内容をGemini経由で取得・要約、または特定の主張がURL内に実在するか検証する。",
    )
    parser.add_argument("url", help="取得対象のURL")
    parser.add_argument(
        "instruction", nargs="*",
        help="追加の指示（省略時は既定の要約指示）。--checkと同時指定は不可",
    )
    parser.add_argument(
        "--check", metavar="CLAIM",
        help="要約の代わりに、この主張がURLの内容で裏付けられるか項目単位で検証する",
    )
    parser.add_argument("--json", action="store_true", help="結果をJSONで出力する")
    parser.add_argument(
        "--model", default="gemini-3.6-flash",
        help="使用するGeminiモデル（既定: gemini-3.6-flash。例: gemini-3.1-pro-preview）",
    )
    args = parser.parse_args()

    if args.check:
        if args.instruction:
            parser.error("--check と追加の指示（自由記述）は同時に指定できません")
        check(args.url, args.check, model=args.model, as_json=args.json)
    else:
        instruction = " ".join(args.instruction) if args.instruction else DEFAULT_INSTRUCTION
        fetch(args.url, instruction, model=args.model)


if __name__ == "__main__":
    main()
