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
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))
from gemini_webfetch import _truncate, fetch_raw, make_client, resolve_redirect  # noqa: E402

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


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？])")
_MARKDOWN_STRIP_RE = re.compile(r"[*_`#>]")
_HAS_DIGIT_RE = re.compile(r"\d")
_TRAILING_PUNCT_RE = re.compile(r"[。．.！!？?\s]+$")


def _clean_for_match(s: str) -> str:
    """Markdown記号と末尾の句読点・空白を除去する。

    grounding_supportsのsegment.textは末尾の句点「。」を含まないことが多く、
    回答本文側（行/文分割後）は句点付きのまま残る。突合前に両側で末尾句読点を
    揃えないと、実際にはgroundedな文が誤って未裏付け扱いになる(false positive)。
    """
    return _TRAILING_PUNCT_RE.sub("", _MARKDOWN_STRIP_RE.sub("", s).strip())


def _split_sentences(text: str) -> list:
    """行を文単位（。！？区切り）にさらに分割し、Markdown記号を除去する。

    grounding_supportsのsegmentは文単位で付与されるため、行単位で突合すると
    1行内の一部だけが裏付けられている場合に他の未裏付け文を見逃す(false negative)。
    """
    sentences = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("---"):
            continue
        for raw in _SENTENCE_SPLIT_RE.split(line):
            cleaned = _clean_for_match(raw)
            if cleaned:
                sentences.append(cleaned)
    return sentences


def audit_grounding(
    text: str,
    grounding_supports: list,
    sources: list,
    chunk_index_to_source: dict[int, int] | None = None,
) -> dict:
    """テキストとgrounding_supportsを突合し、文単位の裏付け状態を監査する。

    注意: grounding_supportsはモデル自身が「この文はこの出典に基づく」と
    申告した自己申告的なメタデータであり、Claude側やユーザーによる独立した
    事実検証ではない。ここでの「裏付けあり」は「出典への帰属が申告されている」
    という意味に過ぎない。

    chunk_index_to_source: grounding_chunk_indicesが指す元chunkのインデックスから
    sources配列のインデックスへの対応表。省略時は「indices[i] == sources[idx]」と
    みなす後方互換動作になるが、非webチャンクが混在するとずれるリスクがある。
    """
    segments = []
    if not grounding_supports:
        return {
            "verified_segments": [],
            "ungrounded_snippets": [],
            "is_fully_grounded": False,
            "audit_unavailable": True,
        }

    for s in grounding_supports:
        seg = getattr(s, "segment", None)
        if not seg or not getattr(seg, "text", None):
            continue
        indices = getattr(s, "grounding_chunk_indices", []) or []
        ref_sources = []
        for idx in indices:
            src_idx = chunk_index_to_source.get(idx) if chunk_index_to_source is not None else idx
            if src_idx is None or src_idx >= len(sources):
                continue
            ref_sources.append({"index": src_idx + 1, "title": sources[src_idx]["title"], "url": sources[src_idx]["url"]})
        segments.append({
            "text": _clean_for_match(seg.text),
            "has_grounding": bool(indices),
            "sources": ref_sources,
        })

    grounded_texts = [s["text"] for s in segments if s["has_grounding"]]

    # 未裏付け文（Un-grounded text）の検出。文単位で判定し、
    # 数字を含む文（数値主張の疑いがある）は短さやボイラープレート一致に関わらず必ず監査する。
    ungrounded_snippets = []
    boilerplate_patterns = ("以下のとおり", "以下の通り", "下記のとおり", "下記の通り", "まとめました", "紹介します", "まとめは以下")
    for sentence in _split_sentences(text):
        has_digit = bool(_HAS_DIGIT_RE.search(sentence))
        if not has_digit:
            if len(sentence) < 15:  # 短い見出しや箇条書きマーカーのみは除外（数字を含む文は対象外にしない）
                continue
            if any(bp in sentence for bp in boilerplate_patterns):
                continue
        # 文がgroundedセグメントに包含されている場合のみ「裏付けあり」とする
        # （逆方向のsegment in sentenceは、短い1句の一致で文全体を誤ってクリアするため使わない）
        is_covered = any(sentence in g for g in grounded_texts)
        if not is_covered:
            ungrounded_snippets.append(sentence)

    return {
        "verified_segments": segments,
        "ungrounded_snippets": ungrounded_snippets,
        "is_fully_grounded": len(ungrounded_snippets) == 0,
        "audit_unavailable": False,
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
    thinking_level: str | None = None,
) -> dict:
    """検索を実行し、回答本文・出典リスト・検索クエリ・裏付け監査を辞書で返す。"""
    client = client or make_client()

    config_kwargs = {
        "tools": [types.Tool(google_search=types.GoogleSearch())],
        "system_instruction": get_system_instruction(),
    }
    if thinking_level is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_level=types.ThinkingLevel[thinking_level.upper()]
        )

    response = client.models.generate_content(
        model=model,
        contents=query,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    sources = []
    # chunk_index_to_source: grounding_chunk_indicesが指す元のchunkインデックス→sources内インデックスの対応。
    # 非webチャンクをスキップするとsourcesの長さがchunksとずれるため、この対応表なしに
    # 「indices[i] == sources配列のインデックス」とみなすと出典の取り違えが起きる。
    chunk_index_to_source: dict[int, int] = {}
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

        for chunk_idx, chunk in enumerate(chunks):
            web = getattr(chunk, "web", None)
            if not web:
                continue
            resolved = resolved_map.get(web.uri) if not no_resolve else None
            chunk_index_to_source[chunk_idx] = len(sources)
            sources.append({
                "title": web.title,
                "url": resolved or web.uri,
                "resolved": bool(resolved),
            })

    audit_result = None
    raw_supports = []
    if grounding:
        raw_supports = getattr(grounding, "grounding_supports", []) or []
    if not no_audit and grounding:
        audit_result = audit_grounding(response.text or "", raw_supports, sources, chunk_index_to_source)

    grounded = bool(sources) and bool(search_queries)

    return {
        "text": response.text or "",
        "sources": sources,
        "search_queries": search_queries,
        "supports_audit": audit_result,
        "grounded": grounded,
        "raw_supports": raw_supports,
        "chunk_index_to_source": chunk_index_to_source,
    }


SEGMENT_CHECK_INSTRUCTION_TEMPLATE = """次の番号付きの各文（segments）について、このページの内容が
それぞれを裏付けるか判定して。各文はモデル自身が「この出典に基づく」と申告した文だが、
それが本当にこのページの内容と一致するかを独立に検証すること。

重要: 「裏付けあり」と判定してよいのは、その文に含まれる日付・数値・固有名詞など
事実要素の**すべて**がこのページの内容と一致する場合のみ。一部の事実だけがページにあり、
他の事実（例: 文の一部にだけ追加された時刻・地域・数値の言い換え等）がページで
確認できない場合は「裏付けあり」にせず「不明」とし、detailに「一致しない部分: ...」
の形でどの部分が裏付けられなかったかを具体的に書くこと。

各項目には、判定の根拠となるページ内の一節を原文のまま「quote」に引用すること。
「裏付けあり」と判定する場合はquoteを空にしてはいけない。

重要: もしこのページの内容を実際に取得できなかった場合は、記憶や推測で判定を埋めてはいけない。
その場合は全項目のverdictを「不明」にし、detailに「ページを取得できなかったため判定不能」と書き、
quoteは空にすること。ページが取得できたが単に文と無関係な内容だった場合は「裏付けなし」を使う。

判定対象の文（segment_idはそのまま出力のidとして使うこと）:
{segments_block}"""


class SegmentCheckItem(BaseModel):
    id: int
    verdict: Literal["裏付けあり", "裏付けなし", "不明"]
    quote: str
    detail: str


class SegmentCheckResult(BaseModel):
    items: list[SegmentCheckItem]


def _build_claim_units(raw_supports: list, sources: list, chunk_index_to_source: dict[int, int]) -> dict[int, dict]:
    """grounding_supportsから「claim単位(id) → {text, urls}」の対応を作る。

    grounding自体が申告した文とその出典URLの対応をそのまま検証単位にすることで、
    text[:500]による打ち切りや、回答全体を1回で丸ごと再分解する無駄を避ける。
    """
    units: dict[int, dict] = {}
    for i, s in enumerate(raw_supports):
        seg = getattr(s, "segment", None)
        if not seg or not getattr(seg, "text", None):
            continue
        indices = getattr(s, "grounding_chunk_indices", []) or []
        urls = []
        for idx in indices:
            src_idx = chunk_index_to_source.get(idx)
            if src_idx is not None and src_idx < len(sources):
                urls.append(sources[src_idx]["url"])
        if not urls:
            continue
        units[i] = {"text": seg.text.strip(), "urls": urls}
    return units


def verify_claim(
    raw_supports: list,
    sources: list,
    chunk_index_to_source: dict[int, int],
    client: genai.Client,
    model: str = "gemini-3.8-flash",
    thinking_level: str | None = None,
) -> dict:
    """grounding_supportsのセグメント単位でclaimを作り、URLごとに1回だけ問い合わせて集約する。

    従来はtext[:500]で打ち切った回答本文を毎回再分解し、出典ごとに独立採点していたため
    (1)回答後半が検証対象から漏れる (2)同じclaimが出典Aで「裏付けあり」出典Bで「裏付けなし」の
    ように無意味に割れる、という問題があった。ここではgrounding自体が申告したclaim→出典の
    対応を単位にし、1URLにつき1回のリクエストで、そのURLに帰属する全claimをまとめて検証する。
    """
    units = _build_claim_units(raw_supports, sources, chunk_index_to_source)
    if not units:
        return {"per_claim": [], "per_source": []}

    # URLごとに、そのURLが出典として付いているclaim(id付き)をまとめる
    url_to_claims: dict[str, list[tuple[int, str]]] = {}
    for claim_id, unit in units.items():
        for url in unit["urls"]:
            url_to_claims.setdefault(url, []).append((claim_id, unit["text"]))

    url_titles = {src["url"]: src["title"] for src in sources}

    def _check_url(url: str, claims: list[tuple[int, str]]) -> dict:
        requested_ids = {cid for cid, _ in claims}
        segments_block = "\n".join(f"- id={cid}: {ctext}" for cid, ctext in claims)
        instruction = SEGMENT_CHECK_INSTRUCTION_TEMPLATE.format(segments_block=segments_block)
        result = fetch_raw(
            url, instruction=instruction, model=model, client=client,
            thinking_level=thinking_level, response_schema=SegmentCheckResult.model_json_schema(),
        )
        try:
            parsed = SegmentCheckResult.model_validate_json(result["text"])
            items = [item.model_dump() for item in parsed.items]
        except Exception:
            items = [
                {"id": cid, "verdict": "不明", "quote": "", "detail": "JSON応答のパースに失敗したため判定不能"}
                for cid, _ in claims
            ]

        # モデルがこのURLに送っていないid（幻覚的なid、または他URL向けidの混入）を
        # 返してくる可能性があるため、実際に送ったid集合でフィルタする。
        items = [item for item in items if item.get("id") in requested_ids]

        if not result["fetch_ok"]:
            reason = result.get("fetch_ng_reason") or "取得ステータスがSUCCESSでない"
            for item in items:
                if item.get("verdict") != "不明":
                    item["detail"] = f"[自動格下げ: {reason}] " + item.get("detail", "")
                    item["verdict"] = "不明"
        for item in items:
            if item.get("verdict") == "裏付けあり" and not item.get("quote"):
                item["detail"] = "[自動格下げ: quoteが空] " + item.get("detail", "")
                item["verdict"] = "不明"

        return {"url": url, "title": url_titles.get(url, url), "items": items, "fetch_ok": result["fetch_ok"]}

    with ThreadPoolExecutor(max_workers=min(MAX_VERIFY_WORKERS, len(url_to_claims))) as pool:
        per_source = list(pool.map(lambda kv: _check_url(kv[0], kv[1]), url_to_claims.items()))

    # claim単位に集約: 1件でも「裏付けあり」（quote付き）があれば裏付けあり、
    # 全出典が「裏付けなし」なら裏付けなし、それ以外は不明。
    per_claim = []
    verdicts_by_claim: dict[int, list[str]] = {cid: [] for cid in units}
    for src_result in per_source:
        for item in src_result["items"]:
            cid = item.get("id")
            if cid in verdicts_by_claim:
                verdicts_by_claim[cid].append(item["verdict"])

    for cid, unit in units.items():
        vs = verdicts_by_claim.get(cid, [])
        if "裏付けあり" in vs:
            final = "裏付けあり"
        elif vs and all(v == "裏付けなし" for v in vs):
            final = "裏付けなし"
        else:
            final = "不明"
        per_claim.append({"id": cid, "text": unit["text"], "urls": unit["urls"], "verdict": final})

    return {"per_claim": per_claim, "per_source": per_source}


def search(
    query: str,
    model: str = "gemini-3.8-flash",
    no_resolve: bool = False,
    as_json: bool = False,
    do_verify: bool = False,
    do_refute: bool = False,
    max_chars: int | None = None,
    no_audit: bool = False,
    no_sources: bool = False,
    thinking_level: str | None = None,
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
        thinking_level=thinking_level,
    )

    verify_skipped_reason = None
    checks = None
    if do_verify:
        if result["raw_supports"]:
            checks = verify_claim(
                result["raw_supports"], result["sources"], result["chunk_index_to_source"],
                client, model=model, thinking_level=thinking_level,
            )
        else:
            verify_skipped_reason = "grounding_supportsが空のため--verify-claimをスキップしました（出典への帰属が一切申告されていません）"

    if as_json:
        payload = {
            "text": _truncate(result["text"], max_chars),
            "search_queries": result["search_queries"],
            "grounded": result["grounded"],
        }
        if not no_sources:
            payload["sources"] = result["sources"]
        if not result["grounded"]:
            payload["warnings"] = ["検索未実行または出典0件：回答は事前学習知識のみの可能性があります"]
        if result["supports_audit"] is not None:
            payload["supports_audit"] = result["supports_audit"]
        if checks is not None:
            payload["claim_checks"] = checks
        elif verify_skipped_reason:
            payload["claim_checks_skipped"] = verify_skipped_reason
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not result["grounded"]:
        print("⚠️ 【検索未実行／出典0件：以下の回答はGoogle検索で裏付けられておらず、事前学習知識のみに基づく可能性があります】\n")

    print(_truncate(result["text"], max_chars))

    if result["search_queries"]:
        print("\n--- 検索クエリ (web_search_queries) ---")
        for q in result["search_queries"]:
            print(f"- {q}")

    if result["sources"] and not no_sources:
        print("\n--- 出典 ---")
        for i, src in enumerate(result["sources"], 1):
            suffix = "" if src["resolved"] or no_resolve else " (解決失敗、リダイレクトURLのまま)"
            print(f"[{i}] {src['title']} - {src['url']}{suffix}")
    elif result["sources"] and no_sources:
        print(f"\n--- 出典 --- ({len(result['sources'])}件、--no-sourcesのため省略)")

    audit = result.get("supports_audit")
    if audit is not None:
        print("\n--- 文単位の裏付け監査 (Grounding Audit) ---")
        print("※ これはモデル自身が申告した出典への帰属をコード側で突合した結果であり、独立した事実検証ではありません。")
        if audit.get("audit_unavailable"):
            print("Status: 監査不能 (grounding_supportsが空のため突合できません。出典への帰属が一切申告されていません)")
        elif audit["is_fully_grounded"]:
            print("Status: 帰属あり・未検証 (すべての主要文章にWeb出典への帰属が申告されています)")
        else:
            print("Status: WARNING (Web出典への帰属が申告されていない文が含まれています)")

        if audit["ungrounded_snippets"]:
            print("\n⚠️ 【出典への帰属が申告されていない文（モデル推測・事前知識の可能性）】:")
            for s in audit["ungrounded_snippets"]:
                print(f"  * {s}")

    if checks is not None:
        print("\n--- 出典の裏付けチェック（--verify-claim、grounding済みの文をclaim単位に集約して判定） ---")
        for claim in checks["per_claim"]:
            print(f"[claim {claim['id']}] {claim['verdict']}  {claim['text']}")
        print("\n(出典URLごとの内訳)")
        for src in checks["per_source"]:
            print(f"  - {src['title']} - {src['url']}")
            for item in src["items"]:
                print(f"      id={item['id']}  {item['verdict']}")
                if item.get("quote"):
                    print(f"        引用: {item['quote']}")
                print(f"        {item['detail']}")
    elif verify_skipped_reason:
        print(f"\n--- --verify-claim: {verify_skipped_reason} ---")


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
        "--no-sources", action="store_true",
        help="出典URL一覧の表示を省略する（コンテキスト節約。一次資料として記録する予定がない一般検索向け。"
             "--verify-claim併用時の出典URL内訳には影響しない）",
    )
    parser.add_argument(
        "--thinking-level", choices=["minimal", "low", "medium", "high"], default=None,
        help="思考プロセス（Thinking）の深さを指定する（既定: モデルごとのデフォルト。gemini-3.8-flashはMEDIUM）。"
             "複雑な論理・数理の突合精度を高めたい場合はhigh推奨",
    )
    args = parser.parse_args()

    search(
        " ".join(args.query),
        model=args.model,
        no_resolve=args.no_resolve,
        as_json=args.json,
        do_verify=args.verify_claim,
        do_refute=args.refute,
        max_chars=args.max_chars,
        no_audit=args.no_audit,
        no_sources=args.no_sources,
        thinking_level=args.thinking_level,
    )


if __name__ == "__main__":
    main()

