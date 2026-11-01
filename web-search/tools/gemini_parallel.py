"""複数のWeb調査をGemini CLI（headless）で並列実行し、結果をファイルに書き出す。

Claude側サブエージェントの代わりにGemini CLIエージェントへ検索・ページ取得・要約を任せ、
Claude側コンテキストには各調査の結論（先頭N文字）とファイルパスだけを流す。

使い方:
  python tools/gemini_parallel.py "調査1" "調査2" ...
  python tools/gemini_parallel.py -f queries.txt      # 1行1調査（空行・#行は無視）
"""
import argparse
import html.parser
import http.client
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).parent))
from gemini_webfetch import (
    _is_empty_quote,
    check_url_alive,
    clean_extracted_url,
    configure_utf8_stdio,
    encode_url_for_request,
    is_low_quality_url,
    is_safe_public_url,
    resolve_redirect,
)

_JST: Final[timezone] = timezone(timedelta(hours=9))
REDIRECT_RE: Final[re.Pattern[str]] = re.compile(
    r"https://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/[\w\-=]+"
)
RAW_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"https?://[^\s\u3000-\u303f\uff00-\uffef\)>\]\"'<>`]+"
)
MD_LINK_OR_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"(!?\[[^\]]*\]\()(https?://[^\s\u3000-\u303f\uff00-\uffef\)>\]\"'<>`]+)(\))"
    r"|https?://[^\s\u3000-\u303f\uff00-\uffef\)>\]\"'<>`]+"
)
_BULLET_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^(\s*(?:[-*+•]|\d+[.)])\s+)")
_TABLE_ROW_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^(\s*\|\s*)")
_TABLE_SEP_RE: Final[re.Pattern[str]] = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")
_CONCLUSION_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(\s*(?:[-*+•]|\d+[.)])?\s*(?:\*\*)*"
    r"(?:【結論】|(?:結論|要約|[Cc]onclusion)(?:\*\*)*(?:\s*[:：]|\s+|$))"
    r"(?:\*\*)*\s*)"
)
_THOUGHT_HEADER_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:💡\s*thought\b|thought\s*:|thinking\b)",
    re.IGNORECASE,
)
_META_MONOLOGUE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*CRITICAL\s+INSTRUCTION\b|(?:I will use\b|I'm querying about\b|Related tools:)",
    re.IGNORECASE,
)
_ANSWER_START_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:(?:\*\*)*(?:結論|【結論】|要約|前提を確認できず|[Cc]onclusion\s*[:：])|"
    r"#+\s+|\|.+\||(?:[-*+•]|\d+[.)])\s+.*(?:\||[\u3040-\u30ff\u4e00-\u9fff]))"
)
_NORM_STRIP_RE: Final[re.Pattern[str]] = re.compile(r"[\s|｜、。．，.,・:：;；!！?？「」『』（）()\[\]【】\"'”’`\-ー―~～]+")
_TRAILING_NON_ASCII_RE: Final[re.Pattern[str]] = re.compile(r"[^\x00-\x7f]+$")
_TRAILING_HIRAGANA_RE: Final[re.Pattern[str]] = re.compile(r"[\u3040-\u309f]+$")
_CHARSET_RE: Final[re.Pattern[str]] = re.compile(r"charset\s*=\s*[\"']?([A-Za-z0-9_\-]+)", re.IGNORECASE)
_META_CHARSET_RE: Final[re.Pattern[str]] = re.compile(
    r"<meta[^>]+charset\s*=\s*[\"']?([A-Za-z0-9_\-]+)",
    re.IGNORECASE,
)
_HALFWIDTH_KANA_RE: Final[re.Pattern[str]] = re.compile(r"[\uff61-\uff9f]")
_PUA_RE: Final[re.Pattern[str]] = re.compile(r"[\ue000-\uf8ff]")
_CTRL_CHAR_RE: Final[re.Pattern[str]] = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_ISO2022_JP_SIGS: Final[tuple[bytes, ...]] = (b"\x1b$B", b"\x1b$@", b"\x1b(J", b"\x1b$(D")
_MAX_FETCH_BYTES: Final[int] = 2 * 1024 * 1024

GUARD: Final[str] = """あなたはWeb調査エージェントです。Google検索とWebページ取得ツールを使って次の調査を行ってください。
規律:
- 検索結果・取得ページに書かれている事実だけを書く。推測・補完・事前知識での穴埋めは禁止。見つからない項目は「記載なし」と書く。
- 各事実は必ず「事実 | 出典の完全なURL（ドメインだけは不可） | 原文引用（ページ内の文言そのまま、60字以内）」の形式で記載する。
- 検索結果に実在しないURLを推測・合成して記載することは厳禁（URLパターンからの推測生成も禁止）。
- 会計年度の表記は必ず決算月を含む「YYYY年M月期」形式（例: 2026年3月期（資料表記: FY25））に統一し、「FY25」「2024年度」「今期」単独の記載は禁止。
- 調査内容に含まれる前提（買収・提携・事業の存在等）を既定事実として扱わず、一次情報で確認できない場合は冒頭で「前提を確認できず」と明記する。金額・数値はいつの時点・どの性質の値か（発表時暫定／完了時確定等）を明記する。
- 前置き・経緯・締めの挨拶は書かない。1行目は必ず「結論: 」で始めて結論を記載し、続けて{max_lines}行以内の箇条書きで答える。
- 今日の日付は{today}。「最新」「現在」はこの日付基準で判断する。

調査内容:
{query}
"""


class _HTMLTextExtractor(html.parser.HTMLParser):
    """HTMLから可視テキストと<title>を抽出する軽量パーサー。"""

    def __init__(self) -> None:
        super().__init__()
        self._in_ignored = False
        self._in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript"):
            self._in_ignored = True
        elif t == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript"):
            self._in_ignored = False
        elif t == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_ignored:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.text_parts.append(data)


def _normalize_for_quote_match(s: str) -> str:
    """NFKC正規化と空白・句読点・記号除去を行い、表記揺れを吸収した比較用文字列を返す。"""
    norm = unicodedata.normalize("NFKC", s).lower()
    return _NORM_STRIP_RE.sub("", norm)


def _normalize_charset_name(name: str) -> str:
    low = name.strip().lower().replace("_", "-")
    if low in ("shift-jis", "sjis", "windows-31j", "ms932", "cp932", "x-sjis"):
        return "cp932"
    if low in ("euc-jp", "eucjp", "x-euc-jp"):
        return "euc_jp"
    if low in ("iso-2022-jp", "csiso2022jp"):
        return "iso2022_jp"
    if low in ("utf8", "utf-8"):
        return "utf-8"
    return name.strip()


def _strict_decode(raw_bytes: bytes, enc: str) -> str | None:
    """strict でデコードする。2MB切り詰め等で末尾1〜3バイトのみが不完全なマルチバイト文字の場合のみ末尾を削って救済する。"""
    try:
        return raw_bytes.decode(enc, errors="strict")
    except LookupError:
        return None
    except UnicodeDecodeError as e:
        if len(raw_bytes) >= 65536 and e.start >= len(raw_bytes) - 3:
            try:
                return raw_bytes[: e.start].decode(enc, errors="strict")
            except (LookupError, UnicodeDecodeError):
                return None
        return None


def _score_decoded_japanese(text: str) -> float:
    """cp932 / euc_jp のデコード結果に対する不自然さスコア（小さいほど良い、先頭64K文字で算出）。"""
    sample = text[:65536]
    n = len(sample)
    if n == 0:
        return 0.0
    hw_kana = len(_HALFWIDTH_KANA_RE.findall(sample))
    pua = len(_PUA_RE.findall(sample))
    ctrl = len(_CTRL_CHAR_RE.findall(sample))
    return (hw_kana / n) * 10.0 + (pua / n) * 20.0 + (ctrl / n) * 20.0


def _decode_html_bytes(raw_bytes: bytes, content_type_header: str = "") -> str:
    """①宣言charset(strict) -> ②ISO-2022-JPエスケープ -> ③utf-8(strict) -> ④cp932/euc_jp採点 -> ⑤utf-8(replace)の順でデコードする。"""
    if not raw_bytes:
        return ""

    # 1. 宣言された文字コード（Content-Type -> 先頭4KBの<meta>）を strict で試行
    candidate_charsets: list[str] = []
    if content_type_header:
        m_ct = _CHARSET_RE.search(content_type_header)
        if m_ct:
            candidate_charsets.append(_normalize_charset_name(m_ct.group(1)))

    head_bytes = raw_bytes[:4096]
    head_ascii = head_bytes.decode("ascii", errors="ignore")
    for m_meta in _META_CHARSET_RE.finditer(head_ascii):
        enc = _normalize_charset_name(m_meta.group(1))
        if enc not in candidate_charsets:
            candidate_charsets.append(enc)

    for enc in candidate_charsets:
        decoded = _strict_decode(raw_bytes, enc)
        if decoded is not None:
            return decoded

    # 2. ISO-2022-JP のエスケープシーケンス検出（先頭4KB）
    if any(sig in head_bytes for sig in _ISO2022_JP_SIGS):
        decoded = _strict_decode(raw_bytes, "iso2022_jp")
        if decoded is not None:
            return decoded

    # 3. utf-8 strict
    decoded_utf8 = _strict_decode(raw_bytes, "utf-8")
    if decoded_utf8 is not None:
        return decoded_utf8

    # 4. 日本語レガシー候補（cp932 / euc_jp）の strict デコード＆採点（同点なら cp932 優先）
    best_text: str | None = None
    best_score: float = float("inf")
    for legacy_enc in ("cp932", "euc_jp"):
        decoded_leg = _strict_decode(raw_bytes, legacy_enc)
        if decoded_leg is not None:
            sc = _score_decoded_japanese(decoded_leg)
            if sc < best_score:
                best_score = sc
                best_text = decoded_leg
    if best_text is not None:
        return best_text

    # 5. 最終フォールバック
    return raw_bytes.decode("utf-8", errors="replace")


def _fetch_page_content(url: str, timeout: float = 10.0) -> dict:
    """URLからHTML本文・タイトルを取得する（最大2MB、SSRF防御・文字コード判定・Content-Type検査付き）。"""
    current_url = encode_url_for_request(url)
    if not is_safe_public_url(current_url):
        return {"status": "BLOCKED", "title": "", "text": "", "truncated": False}

    parsed_path = (urlparse(current_url).path or "").lower()
    if parsed_path.endswith(".pdf"):
        return {"status": "PDF", "title": "", "text": "", "truncated": False}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    raw_bytes = b""
    ctype = ""
    truncated = False
    for _ in range(5):
        if not is_safe_public_url(current_url):
            return {"status": "BLOCKED", "title": "", "text": "", "truncated": False}
        req = urllib.request.Request(current_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                final_url = (resp.geturl() if hasattr(resp, "geturl") else current_url) or current_url
                if final_url != current_url and not is_safe_public_url(final_url):
                    return {"status": "BLOCKED", "title": "", "text": "", "truncated": False}
                ctype = (resp.headers.get("Content-Type") or "") if resp.headers else ""
                media_type = ctype.split(";", 1)[0].strip().lower()
                if media_type == "application/pdf" or "application/pdf" in ctype.lower():
                    return {"status": "PDF", "title": "", "text": "", "truncated": False}
                if media_type and media_type not in ("text/html", "application/xhtml+xml", "text/plain"):
                    return {"status": "SKIP", "title": "", "text": "", "truncated": False}
                raw_bytes = resp.read(_MAX_FETCH_BYTES + 1)
                if len(raw_bytes) > _MAX_FETCH_BYTES:
                    raw_bytes = raw_bytes[:_MAX_FETCH_BYTES]
                    truncated = True
                break
        except PermissionError:
            return {"status": "BLOCKED", "title": "", "text": "", "truncated": False}
        except urllib.error.HTTPError as e:
            code = e.code
            location = e.headers.get("Location") if e.headers else None
            e.close()
            if code in (301, 302, 303, 307, 308) and location:
                next_url = urljoin(current_url, location)
                if not is_safe_public_url(next_url):
                    return {"status": "BLOCKED", "title": "", "text": "", "truncated": False}
                current_url = encode_url_for_request(next_url)
                continue
            return {"status": "ERROR", "title": "", "text": "", "truncated": False}
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), PermissionError) or "SSRF blocked" in str(e):
                return {"status": "BLOCKED", "title": "", "text": "", "truncated": False}
            return {"status": "ERROR", "title": "", "text": "", "truncated": False}
        except (OSError, ValueError, http.client.HTTPException):
            return {"status": "ERROR", "title": "", "text": "", "truncated": False}
    else:
        return {"status": "ERROR", "title": "", "text": "", "truncated": False}

    html_str = _decode_html_bytes(raw_bytes, ctype)
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html_str)
    except Exception:  # noqa: BLE001
        return {"status": "OK", "title": "", "text": html_str, "truncated": truncated}
    return {
        "status": "OK",
        "title": " ".join(parser.title_parts).strip(),
        "text": " ".join(parser.text_parts).strip(),
        "truncated": truncated,
    }


def _prepend_line_tag(line: str, tag: str) -> str:
    """Markdown表の行なら第1セル先頭に、箇条書きならマーカー直後に、それ以外は行頭にタグを付与する。"""
    if _TABLE_SEP_RE.match(line):
        return line
    m_tbl = _TABLE_ROW_PREFIX_RE.match(line)
    if m_tbl:
        prefix = m_tbl.group(1)
        sep = "" if prefix.endswith(" ") else " "
        return f"{prefix}{sep}{tag} {line[len(prefix):]}"
    m_bul = _BULLET_PREFIX_RE.match(line)
    if m_bul:
        prefix = m_bul.group(1)
        return f"{prefix}{tag} {line[len(prefix):]}"
    return f"{tag} {line}"


def _tag_conclusion_line(line: str, tag: str) -> str:
    """結論行（結論: / 【結論】 / 要約 / Conclusion）の見出し直後に警告タグを挿入する。"""
    if _TABLE_ROW_PREFIX_RE.match(line) or "|" in line:
        return line
    m = _CONCLUSION_LINE_RE.match(line)
    if not m:
        return line
    prefix = m.group(1)
    sep = "" if prefix.endswith(" ") else " "
    rest = line[len(prefix):]
    if rest:
        return f"{prefix}{sep}{tag} {rest}"
    return f"{prefix}{sep}{tag}"


def _is_conclusion_line(line: str) -> bool:
    if _TABLE_ROW_PREFIX_RE.match(line) or "|" in line:
        return False
    return bool(_CONCLUSION_LINE_RE.match(line))


def _strip_agent_reasoning_with_status(text: str) -> tuple[str, int, bool]:
    """先頭に混入した内部思考(💡thought / CRITICAL INSTRUCTION等)を除去し、(本文, 除去行数, 空化フラグ)を返す。"""
    if not text or not text.strip():
        return text, 0, False

    lines = text.splitlines()
    idx = 0
    n = len(lines)
    stripped_count = 0
    in_thought_block = False

    while idx < n:
        line = lines[idx]
        s = line.strip()
        if not s:
            if stripped_count > 0:
                in_thought_block = False
                idx += 1
                continue
            break

        if _ANSWER_START_RE.match(line):
            break

        if _THOUGHT_HEADER_RE.match(line):
            in_thought_block = True
            stripped_count += 1
            idx += 1
            continue

        if _META_MONOLOGUE_RE.search(line):
            stripped_count += 1
            idx += 1
            continue

        if in_thought_block:
            stripped_count += 1
            idx += 1
            continue

        break

    if stripped_count == 0:
        return text, 0, False

    remaining = "\n".join(lines[idx:]).strip()
    if not remaining:
        return text, 0, True

    return remaining, stripped_count, False


def _strip_agent_reasoning(text: str) -> tuple[str, int]:
    """先頭に混入した内部思考ブロックを除去し、(除去後テキスト, 除去した思考行数) を返す。"""
    cleaned, count, _empty = _strip_agent_reasoning_with_status(text)
    return cleaned, count


def _classify_url_status(alive: bool, code: int | str) -> str:
    """URLステータスを 'ok' | 'dead' | 'unchecked' に分類する。"""
    if not alive and code in (404, 410):
        return "dead"
    if not alive or code in (401, 403, 429) or isinstance(code, str):
        return "unchecked"
    return "ok"


def _split_pipe_cells(line: str) -> list[str]:
    """パイプ区切り行（箇条書きの | 区切り、または Markdown 表の行）をセル配列に分解する。"""
    s = line.strip().removeprefix("|").removesuffix("|")
    return [c.strip() for c in s.split("|")]


def _candidate_particle_stripped_url(cleaned_u: str) -> str | None:
    """末尾に日本語助詞等が密着している場合（例: https://x.test/aと）、末尾の非ASCII部を除去した候補URLを返す。"""
    m_non_ascii = _TRAILING_NON_ASCII_RE.search(cleaned_u)
    if m_non_ascii and m_non_ascii.start() > 0:
        prefix = cleaned_u[: m_non_ascii.start()]
        if prefix and not prefix.endswith(("/", ":", "?", "&", "=")):
            return prefix
    m_hira = _TRAILING_HIRAGANA_RE.search(cleaned_u)
    if m_hira and m_hira.start() > 0:
        prefix = cleaned_u[: m_hira.start()]
        if prefix and not prefix.endswith(("/", ":", "?", "&", "=")):
            return prefix
    return None


def _postprocess_urls(
    text: str,
    *,
    no_unchecked_tags: bool = False,
    verify_quotes: bool = False,
    subjects: Sequence[str] | None = None,
    return_stats: bool = False,
) -> tuple[str, int, int] | tuple[str, dict]:
    """本文中のgrounding転送URL解決、1パスURL置換、行単位の[UNVERIFIED]格下げ、引用突合、主題外検出を行う。"""
    redirects = set(REDIRECT_RE.findall(text))
    if redirects:
        resolved: dict[str, str | None] = {}
        with ThreadPoolExecutor(max_workers=min(8, len(redirects))) as ex:
            future_to_url = {ex.submit(resolve_redirect, u): u for u in redirects}
            for fut, u in future_to_url.items():
                try:
                    resolved[u] = fut.result()
                except (OSError, RuntimeError, ValueError):
                    resolved[u] = None
        text = REDIRECT_RE.sub(lambda m: resolved.get(m.group(0)) or "(出典URL解決失敗)", text)

    raw_matches = set(RAW_URL_RE.findall(text))
    cleaned_to_encoded: dict[str, str] = {}
    unique_encoded: set[str] = set()
    for raw_u in raw_matches:
        if "grounding-api-redirect" in raw_u:
            continue
        cleaned_u = clean_extracted_url(raw_u)
        if cleaned_u:
            enc_u = encode_url_for_request(cleaned_u)
            cleaned_to_encoded[cleaned_u] = enc_u
            unique_encoded.add(enc_u)

    alive_map: dict[str, tuple[bool, int | str]] = {}
    if unique_encoded:
        with ThreadPoolExecutor(max_workers=min(8, len(unique_encoded))) as ex:
            future_to_u = {ex.submit(check_url_alive, u): u for u in unique_encoded}
            for fut, u in future_to_u.items():
                try:
                    alive_map[u] = fut.result()
                except (OSError, RuntimeError, ValueError):
                    alive_map[u] = (False, "UNREACHABLE")

    # R3-1(4): 助詞等が直後に連続して404となった場合、末尾の非ASCII連続部を落としたURLで再確認する
    effective_cleaned_map: dict[str, str] = {}
    for cleaned_u, enc_u in list(cleaned_to_encoded.items()):
        effective_cleaned_map[cleaned_u] = cleaned_u
        alive, code = alive_map.get(enc_u, (True, 200))
        if not alive and code in (404, 410):
            cand_u = _candidate_particle_stripped_url(cleaned_u)
            if cand_u:
                cand_enc = encode_url_for_request(cand_u)
                if cand_enc not in alive_map:
                    try:
                        alive_map[cand_enc] = check_url_alive(cand_enc)
                    except (OSError, RuntimeError, ValueError):
                        alive_map[cand_enc] = (False, "UNREACHABLE")
                cand_alive, cand_code = alive_map[cand_enc]
                if _classify_url_status(cand_alive, cand_code) != "dead":
                    effective_cleaned_map[cleaned_u] = cand_u
                    cleaned_to_encoded[cand_u] = cand_enc
                    unique_encoded.discard(enc_u)
                    unique_encoded.add(cand_enc)

    # ユニークURL単位の集計（エンコード後URLで一意化）
    url_class: dict[str, str] = {}
    url_low_q: dict[str, bool] = {}
    ok_count = 0
    dead_count = 0
    unchecked_count = 0
    low_quality_count = 0

    for enc_u in unique_encoded:
        alive, code = alive_map.get(enc_u, (True, 200))
        cls = _classify_url_status(alive, code)
        url_class[enc_u] = cls
        if cls == "dead":
            dead_count += 1
        elif cls == "unchecked":
            unchecked_count += 1
        else:
            ok_count += 1

        lq = is_low_quality_url(enc_u)
        url_low_q[enc_u] = lq
        if lq:
            low_quality_count += 1

    # P2/P3: --verify-quotes または --subject 指定時、生存URL(ok)の本文を1回だけ取得してキャッシュ
    page_cache: dict[str, dict] = {}
    subject_list = [s.strip() for s in (subjects or []) if s and s.strip()]
    need_fetch = verify_quotes or bool(subject_list)
    ok_urls = [u for u, cls in url_class.items() if cls == "ok"]
    if need_fetch and ok_urls:
        with ThreadPoolExecutor(max_workers=min(8, len(ok_urls))) as ex:
            future_to_ok = {ex.submit(_fetch_page_content, u): u for u in ok_urls}
            for fut, u in future_to_ok.items():
                try:
                    page_cache[u] = fut.result()
                except Exception:  # noqa: BLE001
                    page_cache[u] = {"status": "ERROR", "title": "", "text": "", "truncated": False}

    # P3: --subject による [OFF-TOPIC] 判定（ユニーク生存URLごと）
    off_topic_urls: set[str] = set()
    if subject_list:
        for u in ok_urls:
            page = page_cache.get(u, {})
            if page.get("status") != "OK":
                continue
            haystack = f"{u} {page.get('title', '')} {page.get('text', '')}".lower()
            if not any(sub.lower() in haystack for sub in subject_list):
                off_topic_urls.add(u)

    def _resolve_raw_url_token(raw_u: str) -> tuple[str, str, str]:
        """raw_u から (表示用effective_u, エンコード済みenc_u, 末尾trailing文字) を返す。"""
        cleaned_u = clean_extracted_url(raw_u)
        if not cleaned_u:
            return raw_u, "", ""
        eff_u = effective_cleaned_map.get(cleaned_u, cleaned_u)
        enc_u = cleaned_to_encoded.get(eff_u) or encode_url_for_request(eff_u)
        trailing = raw_u[len(eff_u):].lstrip("=")
        return eff_u, enc_u, trailing

    # P0 & R3-2: 1パス正規表現コールバック（Markdownインラインリンクは閉じ括弧の直後にタグを配置）
    def _sub_url_or_md_link(m: re.Match[str]) -> str:
        md_prefix = m.group(1)
        if md_prefix is not None:
            raw_u = m.group(2)
            md_close = m.group(3)
        else:
            raw_u = m.group(0)
            md_close = ""

        if "grounding-api-redirect" in raw_u:
            return m.group(0)

        eff_u, enc_u, trailing = _resolve_raw_url_token(raw_u)
        if not enc_u:
            return m.group(0)

        _alive, code = alive_map.get(enc_u, (True, 200))
        cls = url_class.get(enc_u, "ok")

        tags: list[str] = []
        if cls == "dead":
            tags.append(f"[DEAD-LINK: {code}]")
        elif cls == "unchecked" and not no_unchecked_tags:
            tags.append(f"[UNCHECKED: {code}]")
        if url_low_q.get(enc_u):
            tags.append("[LOW-QUALITY-DOMAIN]")
        if enc_u in off_topic_urls:
            tags.append("[OFF-TOPIC]")

        tag_suffix = (" " + " ".join(tags)) if tags else ""
        if md_prefix is not None:
            return f"{md_prefix}{eff_u}{trailing}{md_close}{tag_suffix}"
        return f"{eff_u}{tag_suffix}{trailing}"

    # 行単位の処理（P1: [UNVERIFIED] 格下げ、P2/R3-4/R3-7: 引用突合、R3-3: 表セル先頭配置、R5-1: 裏付けなし集計）
    unverified_lines = 0
    unsupported_lines = 0
    fact_lines_with_urls = 0
    quote_mismatch_count = 0
    no_quote_count = 0
    out_lines: list[str] = []

    for line in text.splitlines():
        if _TABLE_SEP_RE.match(line):
            out_lines.append(line)
            continue

        line_enc_urls: list[str] = []
        for raw_u in RAW_URL_RE.findall(line):
            if "grounding-api-redirect" in raw_u:
                continue
            _eff_u, enc_u, _tr = _resolve_raw_url_token(raw_u)
            if enc_u:
                line_enc_urls.append(enc_u)

        # P2 & R3-4: 各URL列の「次の列」を引用列として突合
        quote_tag: str | None = None
        if verify_quotes and "|" in line and line_enc_urls:
            cells = _split_pipe_cells(line)
            url_quote_pairs: list[tuple[list[str], str]] = []
            for idx_cell, cell_text in enumerate(cells):
                cell_urls: list[str] = []
                for u_in_cell in RAW_URL_RE.findall(cell_text):
                    if "grounding-api-redirect" in u_in_cell:
                        continue
                    _eff, enc, _tr = _resolve_raw_url_token(u_in_cell)
                    if enc:
                        cell_urls.append(enc)
                if cell_urls and idx_cell + 1 < len(cells):
                    url_quote_pairs.append((cell_urls, cells[idx_cell + 1]))

            if url_quote_pairs:
                non_empty_pairs = [(u_list, q_col) for u_list, q_col in url_quote_pairs if not _is_empty_quote(q_col)]
                if not non_empty_pairs:
                    quote_tag = "[NO-QUOTE]"
                    no_quote_count += 1
                else:
                    matched_any = False
                    checked_any_ok_page = False
                    saw_truncated_page = False
                    non_ok_statuses: list[str] = []
                    for u_list, q_col in non_empty_pairs:
                        norm_quote = _normalize_for_quote_match(q_col)
                        for u in u_list:
                            if url_class.get(u) != "ok":
                                continue
                            page = page_cache.get(u, {})
                            p_status = page.get("status", "ERROR")
                            if p_status == "OK":
                                checked_any_ok_page = True
                                if page.get("truncated"):
                                    saw_truncated_page = True
                                norm_body = _normalize_for_quote_match(
                                    f"{page.get('title', '')} {page.get('text', '')}"
                                )
                                if norm_quote and norm_quote in norm_body:
                                    matched_any = True
                                    break
                            else:
                                non_ok_statuses.append(p_status)
                        if matched_any:
                            break

                    if not matched_any:
                        if saw_truncated_page:
                            quote_tag = "[UNCHECKED: TRUNCATED]"
                        elif checked_any_ok_page:
                            quote_tag = "[QUOTE-MISMATCH]"
                            quote_mismatch_count += 1
                        elif non_ok_statuses:
                            first_st = non_ok_statuses[0]
                            if first_st == "PDF":
                                quote_tag = "[UNCHECKED: PDF]"
                            elif first_st in ("SKIP", "TYPE"):
                                quote_tag = "[UNCHECKED: TYPE]"
                            elif first_st == "BLOCKED":
                                quote_tag = "[UNCHECKED: BLOCKED]"
                            else:
                                quote_tag = "[UNCHECKED]"

        replaced_line = MD_LINK_OR_URL_RE.sub(_sub_url_or_md_link, line)

        # P1 & R3-3: 箇条書き行または '|' 区切りの事実行で、URLが存在し全て dead の場合は [UNVERIFIED]
        line_tags: list[str] = []
        is_fact_line = bool(_BULLET_PREFIX_RE.match(replaced_line)) or ("|" in replaced_line)
        if is_fact_line and line_enc_urls:
            fact_lines_with_urls += 1
            has_dead = any(url_class.get(u) == "dead" for u in line_enc_urls)
            has_non_dead = any(url_class.get(u) in ("ok", "unchecked") for u in line_enc_urls)
            if has_dead and not has_non_dead:
                line_tags.append("[UNVERIFIED]")
                unverified_lines += 1

        if quote_tag:
            line_tags.append(quote_tag)

        if line_tags:
            replaced_line = _prepend_line_tag(replaced_line, " ".join(line_tags))

        # R5-1: 裏付けなし行（[UNVERIFIED] / [QUOTE-MISMATCH] / [NO-QUOTE]）を行単位で集計
        if is_fact_line and line_enc_urls:
            has_unsupported_tag = any(
                t in line_tags or t in replaced_line
                for t in ("[UNVERIFIED]", "[QUOTE-MISMATCH]", "[NO-QUOTE]")
            )
            if has_unsupported_tag:
                unsupported_lines += 1

        out_lines.append(replaced_line)

    # R3-5 & R5-1: 結論行の格下げ判定（優先順に評価）
    conclusion_tag: str | None = None
    conclusion_unverified = False
    if (
        (ok_count + unchecked_count) == 0
        or (fact_lines_with_urls > 0 and unsupported_lines == fact_lines_with_urls)
    ):
        conclusion_tag = "[CONCLUSION-UNVERIFIED]"
        conclusion_unverified = True
    elif fact_lines_with_urls > 0 and (unsupported_lines / fact_lines_with_urls) >= 0.5:
        conclusion_tag = "[CONCLUSION-LOW-CONFIDENCE]"
        conclusion_unverified = True

    if conclusion_tag:
        if any(_is_conclusion_line(ln) for ln in out_lines):
            out_lines = [
                _tag_conclusion_line(ln, conclusion_tag) if _is_conclusion_line(ln) else ln
                for ln in out_lines
            ]
        elif fact_lines_with_urls > 0:
            target_plain: str | None = None
            for idx_ln, ln in enumerate(out_lines):
                stripped_ln = ln.strip()
                if not stripped_ln or stripped_ln.startswith(("#", ">")):
                    continue
                if "|" not in stripped_ln and not RAW_URL_RE.search(stripped_ln):
                    target_plain = stripped_ln
                    out_lines[idx_ln] = _prepend_line_tag(ln, conclusion_tag)
                break
            if target_plain is not None:
                for idx_ln, ln in enumerate(out_lines):
                    if ln.strip() == target_plain:
                        out_lines[idx_ln] = _prepend_line_tag(ln, conclusion_tag)

    final_text = "\n".join(out_lines)
    stats = {
        "total_urls": len(unique_encoded),
        "ok_links": ok_count,
        "dead_links": dead_count,
        "unreachable_links": unchecked_count,
        "low_quality_links": low_quality_count,
        "unverified_lines": unverified_lines,
        "unsupported_lines": unsupported_lines,
        "quote_mismatch": quote_mismatch_count,
        "no_quote": no_quote_count,
        "off_topic_links": len(off_topic_urls),
        "conclusion_unverified": conclusion_unverified,
    }
    if return_stats:
        return final_text, stats
    return final_text, dead_count, low_quality_count


def _format_summary_banner(stats: dict) -> str:
    quote_mismatch_total = stats.get("quote_mismatch", 0) + stats.get("no_quote", 0)
    unsupported_n = stats.get("unsupported_lines", stats.get("unverified_lines", 0))
    banner = (
        f"> [検証サマリ] URL {stats['total_urls']}件 / "
        f"生存 {stats['ok_links']} / "
        f"404 {stats['dead_links']} / "
        f"確認不能 {stats['unreachable_links']} / "
        f"低品質 {stats['low_quality_links']} / "
        f"未検証行 {stats['unverified_lines']} / "
        f"引用不一致 {quote_mismatch_total} / "
        f"裏付けなし {unsupported_n}"
    )
    if stats.get("conclusion_unverified"):
        if quote_mismatch_total > 0 or unsupported_n > stats.get("unverified_lines", 0):
            banner += (
                "\n> [警告] 根拠行の多くで、URLが死んでいるか、引用がページに存在しません。"
                "結論は一次資料で未確認として扱ってください。"
            )
        else:
            banner += "\n> [警告] 根拠となる生存URLが不足しています。結論は一次資料で未確認として扱ってください。"
    return banner


def run_one(idx: int, query: str, out_dir: Path, args: argparse.Namespace) -> dict:
    exe = shutil.which("gemini")
    default_stats = {
        "total_urls": 0,
        "ok_links": 0,
        "dead_links": 0,
        "unreachable_links": 0,
        "low_quality_links": 0,
        "unverified_lines": 0,
        "unsupported_lines": 0,
        "quote_mismatch": 0,
        "no_quote": 0,
        "off_topic_links": 0,
        "conclusion_unverified": False,
        "stripped_reasoning_lines": 0,
    }
    if not exe:
        return {
            "idx": idx,
            "query": query,
            "ec": "no_cli",
            "text": "",
            "path": out_dir / f"q{idx:02d}.md",
            "sec": 0,
            **default_stats,
        }
    now_jst = datetime.now(timezone.utc).astimezone(_JST)  # noqa: UP017
    today_str = now_jst.date().isoformat()
    ts_iso = now_jst.isoformat(timespec="seconds")
    prompt = GUARD.format(max_lines=args.max_lines, today=today_str, query=query)
    # Windowsの.cmdシム経由でマルチバイト文字を引数に渡すと文字化けするため、-pにはASCIIのみを渡し本文はstdinで渡す
    cmd = [exe, "--approval-mode", "plan", "-p", "Follow the instructions provided via stdin."]
    if args.model:
        cmd += ["-m", args.model]
    out_path = out_dir / f"q{idx:02d}.md"
    err_path = out_dir / f"q{idx:02d}.stderr.log"
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd,
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=args.timeout,
            cwd=out_dir,
            check=False,
        )
        text, ec = p.stdout.decode("utf-8", "replace").strip(), p.returncode
        err_path.write_bytes(p.stderr)
    except subprocess.TimeoutExpired as exc:
        text, ec = "", "timeout"
        err_bytes = exc.stderr if isinstance(exc.stderr, bytes) else (exc.stderr or "").encode("utf-8", "replace")
        err_path.write_bytes(err_bytes or f"TimeoutExpired after {args.timeout}s\n".encode())

    # R3-8: 先頭に混入した内部思考(💡thought / CRITICAL INSTRUCTION等)を除去
    text, stripped_reasoning_lines, empty_after_strip = _strip_agent_reasoning_with_status(text)

    no_unchecked_tags = getattr(args, "no_unchecked_tags", False)
    verify_quotes = getattr(args, "verify_quotes", False)
    subjects = getattr(args, "subject", None)

    postprocess_err = False
    try:
        processed_res = _postprocess_urls(
            text,
            no_unchecked_tags=no_unchecked_tags,
            verify_quotes=verify_quotes,
            subjects=subjects,
            return_stats=True,
        )
        text, stats = processed_res  # type: ignore[misc]
    except Exception as exc:  # noqa: BLE001
        postprocess_err = True
        stats = dict(default_stats)
        with err_path.open("ab") as f:
            f.write(f"\n[postprocess-error] {exc}\n".encode("utf-8", "replace"))

    stats["stripped_reasoning_lines"] = stripped_reasoning_lines

    elapsed_sec = round(time.time() - t0)
    ok = ec == 0 and bool(text)
    if ok and postprocess_err:
        status_str = "OK(postprocess-error)"
    elif ok and empty_after_strip:
        status_str = "OK(empty-after-strip)"
    elif ok:
        status_str = "OK"
    else:
        status_str = f"FAIL({ec})"
    model_str = args.model or "default"
    escaped_query = query.replace('"', '\\"')
    extra_fm = f"stripped_reasoning_lines: {stripped_reasoning_lines}\n"
    if verify_quotes:
        extra_fm += (
            f"quote_mismatch: {stats['quote_mismatch']}\n"
            f"no_quote: {stats['no_quote']}\n"
        )
    if subjects:
        extra_fm += f"off_topic_links: {stats['off_topic_links']}\n"
    conclusion_unverified_bool = "true" if stats.get("conclusion_unverified") else "false"
    frontmatter = (
        "---\n"
        f'query: "{escaped_query}"\n'
        f'timestamp: "{ts_iso}"\n'
        f'model: "{model_str}"\n'
        f'status: "{status_str}"\n'
        f"elapsed_sec: {elapsed_sec}\n"
        f"dead_links: {stats['dead_links']}\n"
        f"unreachable_links: {stats['unreachable_links']}\n"
        f"low_quality_links: {stats['low_quality_links']}\n"
        f"unverified_lines: {stats['unverified_lines']}\n"
        f"unsupported_lines: {stats['unsupported_lines']}\n"
        f"conclusion_unverified: {conclusion_unverified_bool}\n"
        f"{extra_fm}"
        "---\n\n"
    )
    summary_banner = _format_summary_banner(stats)
    out_path.write_text(f"{frontmatter}{summary_banner}\n\n# {query}\n\n{text}\n", encoding="utf-8")
    return {
        "idx": idx,
        "query": query,
        "ec": ec,
        "text": text,
        "path": out_path,
        "sec": elapsed_sec,
        **stats,
    }


def main() -> None:
    configure_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", nargs="*", help="調査内容（複数可）")
    ap.add_argument("-f", "--file", help="1行1調査のテキストファイル")
    ap.add_argument("-o", "--out-dir", help="出力先（既定: カレント下 gemini_research_<時刻>）")
    ap.add_argument("-j", "--jobs", type=int, default=4, help="並列数（既定4）")
    ap.add_argument("-m", "--model", help="Geminiモデル（既定: Gemini CLIの既定）")
    ap.add_argument("--max-lines", type=int, default=10, help="各回答の最大行数の指示（既定10）")
    ap.add_argument("--preview", type=int, default=400, help="標準出力に出す各回答の先頭文字数。0で非表示（既定400）")
    ap.add_argument("--timeout", type=int, default=300, help="1調査あたりのタイムアウト秒（既定300）")
    ap.add_argument(
        "--no-unchecked-tags",
        action="store_true",
        help="401/403/429や到達不能URLへの [UNCHECKED: ...] タグ付与を抑止する",
    )
    ap.add_argument(
        "--verify-quotes",
        dest="verify_quotes",
        action="store_true",
        default=True,
        help="（既定で有効）生存URLのHTML本文を取得し、3列目の原文引用がページ内に実在するか正規化部分一致で検証する",
    )
    ap.add_argument(
        "--no-verify-quotes",
        dest="verify_quotes",
        action="store_false",
        help="原文引用の実在検証を無効にする（URL取得が増えるのを避けたいとき）",
    )
    ap.add_argument(
        "--subject",
        action="append",
        default=[],
        help="調査主題の固有名詞（複数指定可）。URL・タイトル・本文のいずれにも含まれない出典に [OFF-TOPIC] を付与する",
    )
    args = ap.parse_args()

    queries = list(args.queries)
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            resolved_missing = file_path.resolve()
            sys.exit(
                f"ERROR: クエリファイルが見つかりません: {args.file} (探索先: {resolved_missing})\n"
                "ヒント: `uv run --directory` を使用するとカレントディレクトリがスキルディレクトリに移動します。\n"
                "`-f` や `-o` には絶対パスを指定するか、`uv run --project <skill_dir>` を使用してください。"
            )
        queries += [
            line.strip()
            for line in file_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    if not queries:
        ap.error("調査内容を指定してください")
    if not shutil.which("gemini"):
        sys.exit("ERROR: gemini CLI が見つかりません（npm i -g @google/gemini-cli）")

    ts = datetime.now(timezone.utc).astimezone(_JST).strftime("%Y%m%d_%H%M%S")  # noqa: UP017
    out_dir = Path(args.out_dir or f"gemini_research_{ts}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        results = list(ex.map(lambda iq: run_one(iq[0], iq[1], out_dir, args), enumerate(queries, 1)))

    failed = 0
    dead_query_count = 0
    for r in results:
        ok = r["ec"] == 0 and bool(r["text"])
        failed += not ok
        dead_n = r.get("dead_links", 0)
        unverified_n = r.get("unverified_lines", 0)
        qm_n = r.get("quote_mismatch", 0) + r.get("no_quote", 0)
        if dead_n > 0:
            dead_query_count += 1
        warn_suffix = f" [WARN] dead={dead_n} unverified={unverified_n}" if (dead_n > 0 or unverified_n > 0) else ""
        if r.get("conclusion_unverified"):
            warn_suffix += " ⚠ conclusion-unverified"
        if qm_n > 0:
            warn_suffix += f" quote-mismatch={qm_n}"
        print(f"[q{r['idx']:02d}] {'OK' if ok else 'FAIL(' + str(r['ec']) + ')'} {r['sec']}s {r['path']}{warn_suffix}")
        if args.preview and r["text"]:
            body = r["text"][:args.preview]
            print("  " + body.replace("\n", "\n  ") + (" ..." if len(r["text"]) > args.preview else ""))
    print(f"done: {len(results) - failed}/{len(results)} ok, out_dir={out_dir}")
    if dead_query_count > 0:
        print(f"WARN: {dead_query_count}件の調査に死んだURLを含む")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
