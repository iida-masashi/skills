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
import contextlib
import http.client
import ipaddress
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Literal
from urllib.parse import quote, urljoin, urlparse, urlsplit, urlunsplit

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

ENV_PATH: Final[Path] = Path(os.environ.get("GEMINI_SKILL_ENV_PATH", r"C:\Users\iidam\gemini\.env"))
DEFAULT_MODEL: Final[str] = "gemini-3.8-flash"
THINKING_LEVEL_CHOICES: Final[tuple[str, ...]] = ("minimal", "low", "medium", "high")
FETCH_FAILURE_TOKEN: Final[str] = "RETRIEVAL_FAILED"
DEFAULT_INSTRUCTION: Final[str] = (
    "このページの内容を要約して。ページにない情報は補わず、"
    f"取得できなかった場合は本文全体を「{FETCH_FAILURE_TOKEN}」とだけ出力して。"
)

_MINIMAL_UNSUPPORTED_PREFIXES: Final[tuple[str, ...]] = (
    "gemini-3.8",
    "gemini-4",
    "gemini-3.1-pro",
    "gemini-3-pro",
)

_SECOND_LEVEL_TLDS: Final[frozenset[str]] = frozenset({
    "co.jp", "ne.jp", "or.jp", "go.jp", "ac.jp", "lg.jp", "ed.jp", "ad.jp", "gr.jp",
    "co.uk", "org.uk", "ac.uk", "gov.uk",
    "com.au", "net.au", "org.au", "edu.au", "gov.au",
    "co.kr", "or.kr", "go.kr", "ac.kr",
    "com.br", "com.cn", "com.tw", "com.hk", "com.sg", "com.nz", "co.nz", "co.in", "co.za",
})

_EMPTY_QUOTE_PLACEHOLDERS: Final[frozenset[str]] = frozenset({
    "", "なし", "該当なし", "記載なし", "引用なし", "n/a", "na", "none", "null", "-", "ー", "―",
})

_LOW_QUALITY_EXACT_DOMAINS: Final[frozenset[str]] = frozenset({
    "reddit.com",
    "note.com",
    "ameblo.jp",
    "5ch.net",
    "2ch.sc",
    "chiebukuro.yahoo.co.jp",
    "oshiete.goo.ne.jp",
    "hatenablog.com",
    "hatenablog.jp",
    "hatenadiary.jp",
    "livedoor.jp",
    "fc2.com",
})

_LOW_QUALITY_SUFFIXES: Final[tuple[str, ...]] = (
    ".reddit.com",
    ".note.com",
    ".ameblo.jp",
    ".5ch.net",
    ".2ch.sc",
    ".blog.shinobi.jp",
    ".hatenablog.com",
    ".hatenablog.jp",
    ".hatenadiary.jp",
    ".livedoor.jp",
    ".fc2.com",
)

_WARN_SPAM_DOMAIN_RE: Final[re.Pattern[str]] = re.compile(r"^(?:[\w\-]+\.)*warn[\w\-]*\.com$")
_TRAILING_URL_GARBAGE_RE: Final[re.Pattern[str]] = re.compile(r"[=)\].,;>\"'」』】、。．]+$")


def configure_utf8_stdio() -> None:
    """Windows環境でのcp932エンコードエラーを防ぐため、標準出力・標準エラーをUTF-8に設定する。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with contextlib.suppress(OSError, ValueError):
                reconfigure(encoding="utf-8", errors="replace")


def _is_empty_quote(quote: str | None) -> bool:
    """quoteが空文字、空白のみ、または『なし』『N/A』等のプレースホルダ文字列かを判定する。"""
    if not quote:
        return True
    normalized = quote.strip().strip("\"'「」『』").strip().lower()
    return normalized in _EMPTY_QUOTE_PLACEHOLDERS


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


def resolve_redirect(url: str, timeout: float = 5.0, max_hops: int = 3) -> str | None:
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
    current_url = url
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    for _ in range(max_hops):
        req = urllib.request.Request(current_url, headers=headers)
        try:
            with opener.open(req, timeout=timeout) as resp:
                final_url = resp.geturl()
                return final_url if "grounding-api-redirect" not in final_url else None
        except urllib.error.HTTPError as e:
            try:
                if e.code in (301, 302, 303, 307, 308):
                    location = e.headers.get("Location") if e.headers else None
                    if location:
                        next_url = urljoin(current_url, location)
                        if "grounding-api-redirect" not in next_url:
                            return next_url
                        current_url = next_url
                        continue
            finally:
                e.close()
            return None
        except (OSError, ValueError, http.client.HTTPException):
            return None
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
    except ValidationError:
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

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    creds_missing = False
    if creds_path and not Path(creds_path).exists():
        creds_missing = True
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        print(
            f"[WARN] GOOGLE_APPLICATION_CREDENTIALS file missing ({creds_path}), ignoring.",
            file=sys.stderr,
        )

    use_vertex = (
        os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
        or os.environ.get("GOOGLE_GENAI_USE_ENTERPRISE", "").lower() == "true"
    )
    force_vertex = os.environ.get("GEMINI_SKILL_FORCE_VERTEX", "").lower() == "true"
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if api_key and (not force_vertex or creds_missing):
        if use_vertex and creds_missing:
            print("[WARN] creds file missing, falling back to API key", file=sys.stderr)
        return genai.Client(api_key=api_key, vertexai=False)

    if use_vertex or force_vertex:
        if creds_missing:
            print(
                f"ERROR: GOOGLE_APPLICATION_CREDENTIALS のファイルが見つからず ({creds_path})、"
                "フォールバック先の GEMINI_API_KEY / GOOGLE_API_KEY も設定されていません。",
                file=sys.stderr,
            )
            sys.exit(1)
        return genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        )

    print(
        "ERROR: GEMINI_API_KEY / GOOGLE_API_KEY か Vertex AI設定 "
        "(GOOGLE_GENAI_USE_VERTEXAI=true / GOOGLE_GENAI_USE_ENTERPRISE=true) が見つかりません。",
        file=sys.stderr,
    )
    sys.exit(1)


def normalize_thinking_level(thinking_level: str | None, model: str) -> types.ThinkingLevel | None:
    """モデルに応じたThinkingLevelを返す。minimal非対応モデルの場合は警告を出してLOWへフォールバックする。"""
    if thinking_level is None:
        return None
    level_upper = thinking_level.upper()
    model_lower = model.lower()
    if (
        level_upper == "MINIMAL"
        and "flash-lite" not in model_lower
        and model_lower.startswith(_MINIMAL_UNSUPPORTED_PREFIXES)
    ):
        print(
            f"[WARNING] モデル '{model}' は thinking_level='minimal' に非対応のため 'low' にフォールバックします。",
            file=sys.stderr,
        )
        level_upper = "LOW"
    return types.ThinkingLevel[level_upper]


def extract_response_text(response: object) -> str:
    """Geminiレスポンスから安全に本文テキストを取得する（ブロック時や非テキストパートのみの場合の例外を防ぐ）。"""
    try:
        text = getattr(response, "text", None)
        return text if isinstance(text, str) else ""
    except (ValueError, AttributeError):
        return ""


def apply_claim_safety_downgrades(
    items: list[dict],
    *,
    fetch_ok: bool,
    fetch_failure_reason: str,
) -> None:
    """URL取得失敗時および原文引用(quote)欠落時に、判定(verdict)を機械的に『不明』へ格下げする。"""
    if not fetch_ok:
        for item in items:
            if item.get("verdict") != "不明":
                item["detail"] = (
                    f"[自動格下げ: {fetch_failure_reason}（モデルの判定「{item.get('verdict')}」は採用せず不明扱いとした）] "
                    + item.get("detail", "")
                )
                item["verdict"] = "不明"

    for item in items:
        if item.get("verdict") == "裏付けあり" and _is_empty_quote(item.get("quote")):
            item["quote"] = ""
            item["detail"] = (
                "[自動格下げ: 「裏付けあり」だが原文引用(quote)が空のため不明扱いとした] "
                + item.get("detail", "")
            )
            item["verdict"] = "不明"


def _is_retryable_error(exc: Exception) -> bool:
    """レート制限(429)や一時的なサーバーエラー(5xx)・通信タイムアウトかを判定する。"""
    status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status_code in (408, 429, 500, 502, 503, 504):
        return True
    msg = str(exc).upper()
    retry_tokens = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "502", "504", "TIMED OUT", "TIMEOUT")
    return any(token in msg for token in retry_tokens)


def generate_with_retry(
    client: genai.Client,
    *,
    model: str,
    contents: str,
    config: types.GenerateContentConfig,
    max_retries: int = 3,
    base_delay: float = 1.0,
):
    """一時的なAPIエラー(429/5xx)に対して指数バックオフでリトライを行う。"""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= max_retries or not _is_retryable_error(exc):
                raise
            time.sleep(base_delay * (2 ** attempt))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("generate_with_retry failed without exception")


def _normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host.removeprefix("www.")


def _registrable_domain(host: str) -> str:
    """ホスト名から組織単位の登録ドメイン（例: sub.example.co.jp -> example.co.jp）を返す。"""
    normalized = host.lower().rstrip(".").removeprefix("www.")
    parts = [p for p in normalized.split(".") if p]
    if len(parts) < 2:
        return normalized
    last_two = ".".join(parts[-2:])
    if last_two in _SECOND_LEVEL_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return last_two


def _hosts_match(host_a: str, host_b: str) -> bool:
    """同一ホスト、または同一組織ドメイン（サブドメイン間のリダイレクト等）であればTrueを返す。"""
    if not host_a or not host_b:
        return False
    if host_a == host_b:
        return True
    return _registrable_domain(host_a) == _registrable_domain(host_b)


def is_low_quality_url(url: str) -> bool:
    """SNS・個人ブログ・匿名掲示板・Q&Aサイト・スパム系まとめドメインかを判定する。"""
    host = _normalize_host(url)
    if not host:
        return False
    if host in _LOW_QUALITY_EXACT_DOMAINS:
        return True
    if host.endswith(_LOW_QUALITY_SUFFIXES):
        return True
    return bool(_WARN_SPAM_DOMAIN_RE.match(host))


def clean_extracted_url(url: str) -> str:
    """テキストから抽出した生URL末尾のゴミ文字（リダイレクト置換残骸の'='や閉じ括弧・句読点等）を除去する。"""
    if not url:
        return ""
    return _TRAILING_URL_GARBAGE_RE.sub("", url.strip())


def encode_url_for_request(url: str) -> str:
    """URL内の非ASCII文字をパーセントエンコードする（既存の%XXは二重エンコードしない）。"""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return quote(url, safe=":/?#[]@!$&'()*+,;=%-._~")
    netloc = parts.netloc
    if not netloc.isascii():
        with contextlib.suppress(UnicodeError):
            if "@" in netloc:
                userinfo, _, hostport = netloc.rpartition("@")
                userinfo_enc = quote(userinfo, safe=":!$&'()*+,;=%-._~")
            else:
                userinfo_enc = ""
                hostport = netloc
            host, sep, port = hostport.partition(":")
            host_idna = host.encode("idna").decode("ascii")
            netloc = f"{userinfo_enc + '@' if userinfo_enc else ''}{host_idna}{sep}{port}"
    path = quote(parts.path, safe="/:@!$&'()*+,;=%-._~")
    query = quote(parts.query, safe="/?:@!$&'()*+,;=%-._~")
    fragment = quote(parts.fragment, safe="/?:@!$&'()*+,;=%-._~")
    return urlunsplit((parts.scheme, netloc, path, query, fragment))


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """ループバック・プライベート・リンクローカル・マルチキャスト・予約済み・未指定IPかを判定する。"""
    if (
        isinstance(ip, ipaddress.IPv6Address)
        and ip.ipv4_mapped is not None
        and _is_disallowed_ip(ip.ipv4_mapped)
    ):
        return True
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _parse_ip_candidate(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """通常のIP表記に加え、10進整数(2130706433)や16進/8進表記(0x7f000001等)をIPアドレスとして解釈する。"""
    clean_host = host.strip("[]")
    with contextlib.suppress(ValueError):
        return ipaddress.ip_address(clean_host)

    if re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|0[oO]?[0-7]+|\d+)", clean_host):
        with contextlib.suppress(ValueError):
            val = int(clean_host, 0)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)

    parts = clean_host.split(".")
    if 2 <= len(parts) <= 4 and all(
        re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|0[oO]?[0-7]+|\d+)", p) for p in parts
    ):
        with contextlib.suppress(ValueError):
            nums = [
                int(p, 8 if (p.startswith("0") and len(p) > 1 and not p.lower().startswith(("0x", "0o"))) else 0)
                for p in parts
            ]
            if len(nums) == 4 and all(0 <= n <= 255 for n in nums):
                return ipaddress.IPv4Address((nums[0] << 24) | (nums[1] << 16) | (nums[2] << 8) | nums[3])
            if len(nums) == 2 and 0 <= nums[0] <= 255 and 0 <= nums[1] <= 0xFFFFFF:
                return ipaddress.IPv4Address((nums[0] << 24) | nums[1])
            if len(nums) == 3 and 0 <= nums[0] <= 255 and 0 <= nums[1] <= 255 and 0 <= nums[2] <= 0xFFFF:
                return ipaddress.IPv4Address((nums[0] << 24) | (nums[1] << 16) | nums[2])
    return None


def is_safe_public_url(url: str) -> bool:
    """SSRF対策: http/https以外のスキーム、localhost/.local、プライベート/ループバック等のIPを拒否する。"""
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme.lower() not in ("http", "https"):
        return False

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return False
    if host == "localhost" or host.endswith((".local", ".localhost", ".internal")):
        return False

    ip_cand = _parse_ip_candidate(host)
    if ip_cand is not None:
        return not _is_disallowed_ip(ip_cand)

    try:
        addr_infos = socket.getaddrinfo(host, None)
    except OSError:
        # 数値・16進ドット表記の変形ホストで名前解決に失敗した場合は安全側でブロック、
        # 通常のドメイン名でDNS解決できない場合（テスト用モックドメイン等を含む）は後続のurlopenに委ねる
        return not all(re.fullmatch(r"[0-9a-fA-FxXoO]+", p) for p in host.split(".") if p)

    for info in addr_infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        addr_str = str(sockaddr[0]).split("%", 1)[0]
        ip_obj = _parse_ip_candidate(addr_str)
        if ip_obj is not None and _is_disallowed_ip(ip_obj):
            return False
    return True


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """リダイレクト先URLに対してもSSRF検査を行い、最大5回までに制限するハンドラ。"""

    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        resolved_new = urljoin(req.full_url, newurl)
        if not is_safe_public_url(resolved_new):
            raise PermissionError(f"SSRF blocked redirect to unsafe URL: {resolved_new}")
        return super().redirect_request(req, fp, code, msg, headers, encode_url_for_request(resolved_new))


urllib.request.install_opener(urllib.request.build_opener(SafeRedirectHandler()))


def check_url_alive(url: str, timeout: float = 5.0) -> tuple[bool, int | str]:
    """URLの疎通確認を行い、明確なデッドリンク(404/410)や到達不能・SSRFブロックを検出する。

    403/401/405/429等はBot対策・WAFによるブロックが多いため生存(True)とみなす。
    戻り値は (alive, status_code_or_reason)。
    """
    cleaned = clean_extracted_url(url)
    if not cleaned:
        return False, "EMPTY_URL"
    if "grounding-api-redirect" in cleaned:
        return True, 302

    current_url = encode_url_for_request(cleaned)
    if not is_safe_public_url(current_url):
        return False, "BLOCKED"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Range": "bytes=0-1024",
    }
    for _ in range(5):
        if not is_safe_public_url(current_url):
            return False, "BLOCKED"
        req = urllib.request.Request(current_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                final_url = (resp.geturl() if hasattr(resp, "geturl") else current_url) or current_url
                if final_url != current_url and not is_safe_public_url(final_url):
                    return False, "BLOCKED"
                code = getattr(resp, "status", 200) or 200
                return (code not in (404, 410)), code
        except PermissionError:
            return False, "BLOCKED"
        except urllib.error.HTTPError as e:
            code = e.code
            location = e.headers.get("Location") if e.headers else None
            e.close()
            if code in (301, 302, 303, 307, 308) and location:
                next_url = urljoin(current_url, location)
                if not is_safe_public_url(next_url):
                    return False, "BLOCKED"
                current_url = encode_url_for_request(next_url)
                continue
            if code in (404, 410):
                return False, code
            return True, code
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), PermissionError) or "SSRF blocked" in str(e):
                return False, "BLOCKED"
            return False, "UNREACHABLE"
        except (OSError, ValueError, http.client.HTTPException):
            return False, "UNREACHABLE"
    return False, "UNREACHABLE"


def _is_fetch_ok(statuses: Sequence[dict], requested_url: str | None = None) -> tuple[bool, str | None]:
    """statuses一覧に取得成功(SUCCESS)が1件でも含まれるか判定する共通ヘルパー。

    requested_urlを渡した場合、SUCCESSであってもretrieved_urlのホストが
    要求URLのホスト（または同一登録ドメイン）と一致しない場合はNGとする
    （ログイン壁・別サイトへのリダイレクト等、「何かは取れたが求めたページではない」ケースを
    SUCCESS扱いにしないため）。
    ただし、requested_urlが未解決のgrounding-api-redirect URLである場合は、
    Gemini側でリダイレクト先を取得した結果のホストを受け入れる。
    戻り値は (ok, ng理由 or None)。
    """
    success_statuses = [s for s in statuses if s.get("status") == "URL_RETRIEVAL_STATUS_SUCCESS"]
    if not success_statuses:
        return False, None

    if requested_url is None:
        return True, None

    requested_host = _normalize_host(requested_url)
    is_grounding_redirect = (
        "grounding-api-redirect" in requested_url
        or requested_host == "vertexaisearch.cloud.google.com"
    )
    if is_grounding_redirect:
        return True, None

    for s in success_statuses:
        retrieved = s.get("retrieved_url")
        if retrieved and _hosts_match(_normalize_host(retrieved), requested_host):
            return True, None

    retrieved_hosts = ", ".join(_normalize_host(s.get("retrieved_url") or "") or "(不明)" for s in success_statuses)
    return False, f"取得URLのホスト不一致: 要求={requested_host} 実際={retrieved_hosts}"


def fetch_raw(
    url: str,
    instruction: str = DEFAULT_INSTRUCTION,
    model: str = DEFAULT_MODEL,
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

    config_kwargs: dict = {
        "tools": [types.Tool(url_context=types.UrlContext())],
        "system_instruction": get_system_instruction(),
    }
    normalized_level = normalize_thinking_level(thinking_level, model)
    if normalized_level is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_level=normalized_level
        )
    if response_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_json_schema"] = response_schema

    response = generate_with_retry(
        client,
        model=model,
        contents=f"{instruction}: {url}",
        config=types.GenerateContentConfig(**config_kwargs),
    )

    metadata = response.candidates[0].url_context_metadata if response.candidates else None
    url_metas = getattr(metadata, "url_metadata", None) if metadata else None
    statuses = []
    if url_metas:
        for m in url_metas:
            status_obj = getattr(m, "url_retrieval_status", None)
            status_name = getattr(status_obj, "name", str(status_obj)) if status_obj else "UNKNOWN"
            statuses.append({"status": status_name, "retrieved_url": getattr(m, "retrieved_url", None)})

    fetch_ok, ng_reason = _is_fetch_ok(statuses, requested_url=url)

    return {
        "text": extract_response_text(response),
        "statuses": statuses,
        "fetch_ok": fetch_ok,
        "fetch_ng_reason": ng_reason,
        "requested_url": url,
    }


def check_claim_raw(
    url: str,
    claim: str,
    model: str = DEFAULT_MODEL,
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

    statuses = result["statuses"]
    if result.get("fetch_ng_reason"):
        failure_reason = f"URL取得ステータスが{result['fetch_ng_reason']}のため"
    else:
        status_names = ", ".join(s["status"] for s in statuses) if statuses else "ステータス不明（取得情報なし）"
        failure_reason = f"URL取得ステータスが{status_names}のため"

    apply_claim_safety_downgrades(
        items,
        fetch_ok=result["fetch_ok"],
        fetch_failure_reason=failure_reason,
    )

    return {"url": result.get("requested_url", url), "items": items, "statuses": statuses, "fetch_ok": result["fetch_ok"]}


def _truncate(text: str, max_chars: int | None) -> str:
    if not max_chars or len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...(以下{len(text) - max_chars}文字を省略。全文が必要な場合は--max-charsを外すか増やす)"


def fetch(
    url: str,
    instruction: str = DEFAULT_INSTRUCTION,
    model: str = DEFAULT_MODEL,
    max_chars: int | None = None,
    thinking_level: str | None = None,
    as_json: bool = False,
) -> None:
    result = fetch_raw(url, instruction, model, thinking_level=thinking_level)
    text = result["text"]
    suspect_failure = not result["fetch_ok"] or FETCH_FAILURE_TOKEN in text or not text.strip()

    if as_json:
        payload = {
            "url": result.get("requested_url", url),
            "text": _truncate(text, max_chars),
            "statuses": result["statuses"],
            "fetch_ok": result["fetch_ok"] and not suspect_failure,
            "fetch_ng_reason": result.get("fetch_ng_reason"),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if result["statuses"]:
        print("--- 取得ステータス ---")
        for s in result["statuses"]:
            print(f"{s['status']}  {s['retrieved_url']}")
        print()
    else:
        print("--- 取得ステータス ---\n(取得情報なし：url_context_metadataが返されていません)\n")

    if suspect_failure:
        reason = f"（{result['fetch_ng_reason']}）" if result.get("fetch_ng_reason") else ""
        print(f"[WARNING] 【取得失敗の疑い{reason}：以下の内容は正常に取得できたページの要約ではない可能性があります】\n")

    print(_truncate(text, max_chars))


def check(
    url: str,
    claim: str,
    model: str = DEFAULT_MODEL,
    as_json: bool = False,
    thinking_level: str | None = None,
) -> None:
    result = check_claim_raw(url, claim, model=model, thinking_level=thinking_level)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"URL: {result.get('url', url)}")
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
    configure_utf8_stdio()
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
        "--model", default=DEFAULT_MODEL,
        help=f"使用するGeminiモデル（既定: {DEFAULT_MODEL}。例: gemini-4-argon, gemini-3.5-flash-lite）",
    )
    parser.add_argument(
        "--max-chars", type=int, default=None,
        help="回答本文をこの文字数で打ち切る（呼び出し元＝Claude側のコンテキスト消費を抑えたい時に指定。--checkには影響しない）",
    )
    parser.add_argument(
        "--thinking-level", choices=list(THINKING_LEVEL_CHOICES), default=None,
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
        fetch(
            args.url,
            instruction,
            model=args.model,
            max_chars=args.max_chars,
            thinking_level=args.thinking_level,
            as_json=args.json,
        )


if __name__ == "__main__":
    main()
