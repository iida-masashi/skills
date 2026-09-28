"""
Gemini API (URL context tool) を使ったWebFetchツール。

Claude CodeのWebFetchツールの代替。指定URLの内容をGemini経由で取得・要約する。
証明書エラー等でClaude側のWebFetchが失敗するサイトでも、Google側の取得経路を
使うため成功することがある(ただし取得元は同じインターネット上のサイトであり、
Geminiが実際にライブ取得したかキャッシュを使ったかはurl_retrieval_statusでしか
判別できない点に注意)。

使い方:
    cd claude-gemini-skills/web-search && uv run python tools/gemini_webfetch.py <URL> ["追加の指示"]

追加の指示を省略した場合はDEFAULT_INSTRUCTION（要約＋グラウンディング規律＋取得失敗トークン指示）を使う。

APIキー/Vertex AI設定は既定で C:/Users/iidam/gemini/.env から読み込む
(環境変数 GEMINI_SKILL_ENV_PATH で上書き可能)。

出力:
    Geminiの回答本文と、URL取得ステータス(成功/失敗)。
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from google import genai
from google.genai import types
from pydantic import BaseModel

ENV_PATH = Path(os.environ.get("GEMINI_SKILL_ENV_PATH", r"C:\Users\iidam\gemini\.env"))
FETCH_FAILURE_TOKEN = "RETRIEVAL_FAILED"
DEFAULT_INSTRUCTION = (
    "このページの内容を要約して。ページにない情報は補わず、"
    f"取得できなかった場合は本文全体を「{FETCH_FAILURE_TOKEN}」とだけ出力して。"
)


def get_system_instruction() -> str:
    """websearch側と同趣旨のグラウンディング規律。出力フォーマットの指示は含めない
    （--checkのJSON専用指示、fetchの要約指示と競合させないため）。"""
    return (
        "あなたは厳格な事実調査アシスタントです。\n"
        "【絶対規律】\n"
        "1. 指定URLの実際のページ内容に明確に記載されている事実・数値のみを回答してください。\n"
        "2. ページに書かれていない数値や事実を、あなたの事前学習知識や推測で補完・創作することは厳禁です。\n"
        "3. ページの記載内容と異なる、またはページから確認できない場合は、その旨を正直に回答してください。"
    )


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """302/301リダイレクトを自動追従せず、Locationヘッダーをキャプチャするハンドラ。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def resolve_redirect(url: str, timeout: float = 5.0) -> str | None:
    """grounding-api-redirect URLを実URLに解決する。失敗時はNone。
    
    Googleのgrounding-api-redirectはHTTP 302 Foundで実URLを返す。
    リダイレクト先サイトへの接続・ページダウンロードを行わずにLocationヘッダーのみを取得することで、
    相手先サーバーの403ブロックや巨大PDFダウンロードによるタイムアウトを回避する。
    """
    if not url:
        return None
    if "grounding-api-redirect" not in url:
        return url

    opener = urllib.request.build_opener(NoRedirectHandler)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        resp = opener.open(req, timeout=timeout)
        return resp.geturl()
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            location = e.headers.get("Location")
            if location:
                return location
        return None
    except Exception:
        return None


CHECK_INSTRUCTION_TEMPLATE = """次の主張を、否定できない事実の最小単位ごとに箇条書きに分解し、
このページの内容が各項目を裏付けるか判定して。

重要: 分解した1項目の中に複数の事実要素（日付・数値・固有名詞等）が残ってしまった場合、
「裏付けあり」と判定してよいのはその要素の**すべて**がページ内容と一致する場合のみ。
一部だけ一致し他が確認できない場合は「不明」とし、detailにどの部分が裏付けられなかったかを書くこと。

各項目には、判定の根拠となるページ内の一節を原文のまま「quote」に引用すること。
「裏付けあり」と判定する場合はquoteを空にしてはいけない。

重要: もしこのページの内容を実際に取得できなかった場合（アクセスエラー、ページが空、
無関係なエラーページしか見えない等）は、記憶や推測で判定を埋めてはいけない。
その場合は全項目のverdictを「不明」にし、detailに「ページを取得できなかったため判定不能」と書き、
quoteは空にすること。
ページが取得できたが単に主張と無関係な内容だった場合は「裏付けなし」を使い、
取得できなかった場合の「不明」とは区別すること。

主張: {claim}"""


class CheckItem(BaseModel):
    claim: str
    verdict: Literal["裏付けあり", "裏付けなし", "不明"]
    quote: str
    detail: str


class CheckResult(BaseModel):
    items: list[CheckItem]


def _parse_check_json(text: str) -> list[dict] | None:
    """--checkの応答を構造化出力スキーマ(CheckResult)でパースする。失敗時はNone。"""
    if not text:
        return None
    try:
        result = CheckResult.model_validate_json(text)
    except Exception:
        return None
    return [item.model_dump() for item in result.items]


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


def _normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _is_fetch_ok(statuses: list, requested_url: str | None = None) -> tuple[bool, str | None]:
    """statuses一覧に取得成功(SUCCESS)が1件でも含まれるか判定する共通ヘルパー。

    requested_urlを渡した場合、SUCCESSであってもretrieved_urlのホストが
    要求URLのホストと一致しない場合はNGとする（ログイン壁・別ページへのリダイレクト等、
    「何かは取れたが求めたページではない」ケースをSUCCESS扱いにしないため）。
    戻り値は (ok, ng理由 or None)。
    """
    success_statuses = [s for s in statuses if s["status"] == "URL_RETRIEVAL_STATUS_SUCCESS"]
    if not success_statuses:
        return False, None

    if requested_url is None:
        return True, None

    requested_host = _normalize_host(requested_url)
    for s in success_statuses:
        retrieved = s.get("retrieved_url")
        if retrieved and _normalize_host(retrieved) == requested_host:
            return True, None

    retrieved_hosts = ", ".join(_normalize_host(s.get("retrieved_url") or "") or "(不明)" for s in success_statuses)
    return False, f"取得URLのホスト不一致: 要求={requested_host} 実際={retrieved_hosts}"


def fetch_raw(
    url: str,
    instruction: str = DEFAULT_INSTRUCTION,
    model: str = "gemini-3.8-flash",
    client: genai.Client | None = None,
    thinking_level: str | None = None,
    response_schema: dict | None = None,
) -> dict:
    """URLを取得しGeminiの回答本文・取得ステータスを辞書で返す（他スクリプトからの再利用向け）。"""
    if "grounding-api-redirect" in url:
        resolved = resolve_redirect(url)
        if resolved:
            url = resolved

    client = client or make_client()

    config_kwargs = {
        "tools": [types.Tool(url_context=types.UrlContext())],
        "system_instruction": get_system_instruction(),
    }
    if thinking_level is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_level=types.ThinkingLevel[thinking_level.upper()]
        )
    if response_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_json_schema"] = response_schema

    response = client.models.generate_content(
        model=model,
        contents=f"{instruction}: {url}",
        config=types.GenerateContentConfig(**config_kwargs),
    )

    metadata = response.candidates[0].url_context_metadata if response.candidates else None
    url_metas = getattr(metadata, "url_metadata", None) if metadata else None
    statuses = []
    if url_metas:
        for m in url_metas:
            statuses.append({"status": m.url_retrieval_status.name, "retrieved_url": m.retrieved_url})

    fetch_ok, ng_reason = _is_fetch_ok(statuses, requested_url=url)

    return {
        "text": response.text or "",
        "statuses": statuses,
        "fetch_ok": fetch_ok,
        "fetch_ng_reason": ng_reason,
        "requested_url": url,
    }


def check_claim_raw(
    url: str,
    claim: str,
    model: str = "gemini-3.8-flash",
    client: genai.Client | None = None,
    thinking_level: str | None = None,
) -> dict:
    """主張を項目単位に分解し、URLの内容が各項目を裏付けるか判定する（他スクリプトからの再利用向け）。"""
    instruction = CHECK_INSTRUCTION_TEMPLATE.format(claim=claim)
    result = fetch_raw(
        url, instruction=instruction, model=model, client=client,
        thinking_level=thinking_level, response_schema=CheckResult.model_json_schema(),
    )
    items = _parse_check_json(result["text"])
    if items is None:
        # スキーマ通りのJSON化に失敗した場合はraw textを1項目として扱う（完全なフォールバック）
        items = [{"claim": claim, "verdict": "不明", "quote": "", "detail": result["text"][:300]}]

    # モデルの自己申告（プロンプトの指示）だけに頼らず、コード側でも取得ステータスを
    # 強制チェックする。SUCCESS以外なのに「裏付けあり/なし」と断定してくる場合が
    # 実際に観測されているため（Geminiが検索インデックスのキャッシュ等から
    # それらしい判定を埋めてしまう one-off のハルシネーション）、
    # ここで機械的に「不明」へ格下げし、理由を明記する。
    statuses = result["statuses"]
    if not result["fetch_ok"]:
        if result.get("fetch_ng_reason"):
            status_names = result["fetch_ng_reason"]
        else:
            status_names = ", ".join(s["status"] for s in statuses) if statuses else "ステータス不明（取得情報なし）"
        for item in items:
            if item.get("verdict") != "不明":
                item["detail"] = (
                    f"[自動格下げ: URL取得ステータスが{status_names}のため、"
                    f"モデルの判定「{item.get('verdict')}」は採用せず不明扱いとした] " + item.get("detail", "")
                )
                item["verdict"] = "不明"

    # 「裏付けあり」なのにquote（原文引用）が空の場合は、根拠のない断定の疑いがあるため格下げする。
    # ページに実際にその引用が存在するかまでは検証していないが、最低限の裏取りの痕跡を要求する。
    for item in items:
        if item.get("verdict") == "裏付けあり" and not item.get("quote"):
            item["detail"] = "[自動格下げ: 「裏付けあり」だが原文引用(quote)が空のため不明扱いとした] " + item.get("detail", "")
            item["verdict"] = "不明"

    return {"url": url, "items": items, "statuses": statuses, "fetch_ok": result["fetch_ok"]}


def _truncate(text: str, max_chars: int | None) -> str:
    if not max_chars or len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...(以下{len(text) - max_chars}文字を省略。全文が必要な場合は--max-charsを外すか増やす)"


def fetch(
    url: str,
    instruction: str = DEFAULT_INSTRUCTION,
    model: str = "gemini-3.8-flash",
    max_chars: int | None = None,
    thinking_level: str | None = None,
) -> None:
    result = fetch_raw(url, instruction, model, thinking_level=thinking_level)

    if result["statuses"]:
        print("--- 取得ステータス ---")
        for s in result["statuses"]:
            print(f"{s['status']}  {s['retrieved_url']}")
        print()
    else:
        print("--- 取得ステータス ---\n(取得情報なし：url_context_metadataが返されていません)\n")

    text = result["text"]
    if not result["fetch_ok"] or FETCH_FAILURE_TOKEN in text or not text.strip():
        reason = f"（{result['fetch_ng_reason']}）" if result.get("fetch_ng_reason") else ""
        print(f"⚠️ 【取得失敗の疑い{reason}：以下の内容は正常に取得できたページの要約ではない可能性があります】\n")

    print(_truncate(text, max_chars))


def check(url: str, claim: str, model: str = "gemini-3.8-flash", as_json: bool = False, thinking_level: str | None = None) -> None:
    result = check_claim_raw(url, claim, model=model, thinking_level=thinking_level)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"URL: {url}")
    print(f"主張: {claim}\n")
    for i, item in enumerate(result["items"], 1):
        print(f"[{i}] {item['verdict']}  {item['claim']}")
        if item.get("quote"):
            print(f"    引用: {item['quote']}")
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
        "--model", default="gemini-3.8-flash",
        help="使用するGeminiモデル（既定: gemini-3.8-flash。例: gemini-3.1-pro-preview）",
    )
    parser.add_argument(
        "--max-chars", type=int, default=None,
        help="回答本文をこの文字数で打ち切る（呼び出し元＝Claude側のコンテキスト消費を抑えたい時に指定。--checkには影響しない）",
    )
    parser.add_argument(
        "--thinking-level", choices=["minimal", "low", "medium", "high"], default=None,
        help="思考プロセス（Thinking）の深さを指定する（既定: モデルごとのデフォルト）。--checkで判定精度を上げたい場合はhigh推奨",
    )
    args = parser.parse_args()

    if args.check:
        if args.instruction:
            parser.error("--check と追加の指示（自由記述）は同時に指定できません")
        check(args.url, args.check, model=args.model, as_json=args.json, thinking_level=args.thinking_level)
    else:
        if args.instruction:
            user_instruction = " ".join(args.instruction)
            instruction = (
                f"{user_instruction} ページにない情報は補わず、"
                f"取得できなかった場合は本文全体を「{FETCH_FAILURE_TOKEN}」とだけ出力して。"
            )
        else:
            instruction = DEFAULT_INSTRUCTION
        fetch(args.url, instruction, model=args.model, max_chars=args.max_chars, thinking_level=args.thinking_level)


if __name__ == "__main__":
    main()
