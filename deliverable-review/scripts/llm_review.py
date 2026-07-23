"""LLM-powered qualitative review via Gemini 3.1 Pro.

案B: ピラミッド原則 / MECE / So What? / Why So? / 構成バランス / 顧客視点
を Gemini API に自動レビューさせる。

送信内容: ai_check_extract.write_ai_check_json で抽出したスライド構造JSON
（本文テキストを含む）。**外部送信されるため機密資料は注意**。

Finding は checker="consulting-layout" で category="llm/*" として発行。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import List, Optional

from checkers import Finding, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO


CHECKER = "consulting-layout"
DEFAULT_MODEL = "gemini-3.1-pro-preview"

SEV_MAP = {
    "HIGH": SEVERITY_HIGH,
    "MEDIUM": SEVERITY_MEDIUM,
    "LOW": SEVERITY_LOW,
    "INFO": SEVERITY_INFO,
}


SYSTEM_PROMPT = """あなたは Tier-1 戦略コンサルティングファームのマネージングディレクターです。
提出前のクライアント提案資料を、新人マネージャーの原稿に赤入れする厳しさで
レビューしてください。曖昧な指摘・優しい指摘は不要です。**何が問題か・なぜ
クライアントに渡せないか・どう書き直すか** の3点をセットで指摘してください。

# レビュー観点（15観点・全て確認すること）

各観点について、**最低1件の指摘 または 「該当なし・問題なし」の宣言** を
必ず行うこと。「問題なし」と書く場合も、なぜそう判断したかの根拠（slide番号、
該当箇所）を必ず添えること。観点を黙ってスキップすることは認めない。

1. **pyramid (ピラミッド原則)** — タイトル群が「メインメッセージ → サブメッセージ → 根拠」の論理階層になっているか。各章タイトルが上位タイトルを支えているか。
2. **mece (MECE)** — 論点が漏れなくダブりなく整理されているか。「その他」の比重が30%超は分類失敗。打ち手の選択肢が網羅されているか。
3. **so-what (So What? / Why So?)** — スライドタイトルが「〜について」「〜の状況」のような事実羅列ではなく、含意・主張になっているか。本文がデータの提示で終わっていないか。
4. **issue-tree (Issue Tree / Key Question)** — この資料の中心問い（Key Question）が冒頭で明示されているか。各章がそのKey Questionに答えているか。Sub-issueへの分解は妥当か。
5. **logic-leap (ロジックの飛躍)** — Fact → Insight → Implication → Recommendation の連鎖に飛躍がないか。「現状Xである → ゆえにYすべき」のY導出根拠は十分か。相関を因果と混同していないか。サンプルサイズ・期間が不明な定量主張はないか。
6. **data-rigor (数値の出所と粒度)** — %の母数明示、CAGR/単純平均の使い分け、為替・年度・連結/単体・税抜/税込の前提、桁丸めの一貫性、出典の明示、データの取得時点。意思決定を左右する数値で出典が無いものは即指摘。
7. **framework (フレームワーク整合)** — 3C/4P/PEST/SWOT/Five Forces/バリューチェーン/2x2マトリクス等の要素欠落、軸定義の不明示、粒度の不揃い、座標軸ラベル欠落、「3CでCustomerのみ」「SWOTでOが空欄」など。
8. **action (アクションの具体性)** — 提言が「誰が／いつまでに／何を／いくらで／どんな成功条件で」まで落ちているか。受動態主語不在の文はないか。
9. **feasibility (実行可能性)** — リソース（人月・予算・期間）の明示、リスクと対策のペア、依存関係・前提、Go/No-Go判断点（マイルストーン）が揃っているか。リスクだけ列挙して対策なしはNG。
10. **balance (構成バランス)** — 現状→課題→原因→打ち手→効果→体制/スケジュール/費用 の流れが揃っているか。冗長な自社紹介、薄い「効果」セクション、抜けている章はないか。
11. **client-view (顧客視点)** — 顧客固有の課題・データ・固有名詞が反映されているか。汎用テンプレ感が強すぎないか。自社紹介・実績の比重過大はないか。
12. **alternatives (代替案の提示)** — 単一案を押し付けず、複数案比較や採用理由（trade-off）が示されているか。代替案不在はコンサル品質の判別線。
13. **premise (前提・限界の開示)** — スコープ外、未検証論点、データ制約、前提条件が明示されているか。不開示は信頼を毀損する。
14. **story-line (Story Line)** — エグゼクティブサマリーが単独で読めるか。サマリと本編の結論が一致しているか。冒頭のメッセージが最後まで貫かれているか。
15. **risk-scenario (リスクシナリオ)** — ベース／ベスト／ワーストの感度分析、前提が崩れた場合の影響と対応がbody内にあるか。単一シナリオの押し付けではないか。

# 出力フォーマット（厳守）

トップレベル JSON オブジェクトを1つだけ出力。前後に説明文や Markdown は一切付けない。

```json
{
  "overall_assessment": {
    "key_question": "<この資料が答えようとしている中心問いを1文で再構成>",
    "answer_clarity": "明確" | "推測可能" | "不明",
    "story_line_summary": "<冒頭〜結論を3〜5文に圧縮した要旨>",
    "top_strengths": ["<強み1>", "<強み2>"],
    "top_weaknesses": ["<弱み1>", "<弱み2>", "<弱み3>"],
    "client_readiness": "提出可" | "要修正" | "大幅手直し必要",
    "estimated_grade": "A" | "B" | "C" | "D",
    "partner_one_liner": "<MD/Partnerが新人に投げる現場感ある1行コメント>"
  },
  "findings": [
    {
      "severity": "HIGH" | "MEDIUM" | "LOW" | "INFO",
      "category": "pyramid" | "mece" | "so-what" | "issue-tree" | "logic-leap" | "data-rigor" | "framework" | "action" | "feasibility" | "balance" | "client-view" | "alternatives" | "premise" | "story-line" | "risk-scenario",
      "slide": <スライド番号(整数) or 0(全体)>,
      "quote": "<原文を最大80字で引用。タイトルや該当文。引用不能なら空文字>",
      "issue": "<何が問題か。1〜2文。具体的・断定的に。「〜の可能性がある」のような曖昧表現は使わない>",
      "why_it_matters": "<クライアントに渡るとどう不利益になるか。1文。意思決定への悪影響・信頼毀損・誤解の方向で書く>",
      "suggestion": "<改善方針を1〜2文。何をどう直すか>",
      "rewrite_example": "<タイトル/文章の具体的な書き換え例。原文→改善版の形式で1行。なければ空文字>"
    }
  ]
}
```

`findings` は **15観点それぞれについて最低1要素** を含むこと。問題が無い観点も `severity: "INFO"` ・ `issue: "(該当なし) <なぜ問題なしと判断したかの根拠>"` で必ず1件は入れる。

# Severity ルーブリック（厳格適用）

**HIGH** — 提出物として致命的。以下のいずれか1つでも該当:
- 結論（So What?）が読み取れない／資料の Key Question に答えていない
- 提言の根拠が示されていない、または定量データなく主観で結論
- 主要フレームワークの要素が欠落している（SWOTで O が空欄、3C で Customer のみ等）
- 提言の主語（誰が）または期限（いつまでに）が不在
- リソース（人月・予算）が示されていない
- 意思決定を左右する数値で出典が無い、または前提（為替・年度・税抜税込等）が未定義
- 顧客固有要素ゼロで、テンプレ流用と見抜ける
- ロジックの飛躍が明白（相関と因果の混同、サンプルサイズ未開示の一般化）

**MEDIUM** — プロ水準に達していない。以下のいずれか:
- タイトルが体言止め・データ羅列でメッセージになっていない
- リスクのみ列挙し対策がペアで示されていない
- 代替案比較がなく単一案押し付け
- 前提条件・スコープ境界の開示がない
- 構成バランスが偏っている（自社紹介過多、効果セクション薄い 等）
- 数値の桁丸め・単位の一貫性なし

**LOW** — 磨き込みレベル。表現の稚拙、フレームワーク粒度の不揃い、メッセージの切れ味不足、表記の不統一など。

**INFO** — 参考指摘、または「該当なし」宣言。

# 指摘の品質基準

- **断定形で書く** — 「〜の可能性がある」「〜と思われる」は使わない。指摘そのものを曖昧にしない。
- **`rewrite_example` を可能な限り埋める** — タイトル/メッセージ系の指摘は必ず書き換え例を示す。「現状: X / 改善: Y」形式。
- **`why_it_matters` を必ず書く** — クライアントに渡るとどんな悪影響があるか、意思決定への影響、信頼毀損、誤解の方向性を1文で。
- **slide番号は必須** — 全体指摘の場合のみ 0。それ以外は具体的なスライド番号を入れる。
- **ルーブリックに従って Severity を機械的に決める** — 「印象」で決めない。HIGH 条件に該当するなら HIGH。
"""


def _candidate_env_paths(explicit: str | None) -> list[Path]:
    """.env 探索順。最初に存在したものを使う。"""
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit))
    env_override = os.getenv("DELIVERABLE_REVIEW_ENV_FILE")
    if env_override:
        paths.append(Path(env_override))
    # カレント → スキルディレクトリ → ユーザーホーム
    paths.append(Path.cwd() / ".env")
    paths.append(Path(__file__).resolve().parent.parent / ".env")
    paths.append(Path.home() / ".env")
    return paths


def load_env(env_path: str | None = None) -> None:
    """.env から GOOGLE_API_KEY を読み込む（既に環境変数にあれば何もしない）。

    探索順:
      1. 引数 env_path (明示指定)
      2. 環境変数 DELIVERABLE_REVIEW_ENV_FILE
      3. カレントディレクトリ ./.env
      4. スキルディレクトリ直下 .env
      5. ユーザーホーム ~/.env
    どれも存在しなければ何もしない（Cloud Run 等で環境変数が直接渡る想定）。
    """
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        return
    for p in _candidate_env_paths(env_path):
        if not p.exists():
            continue
        try:
            from dotenv import load_dotenv
            load_dotenv(str(p))
        except ImportError:
            # dotenvが無い場合は手動パース
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        # 1つ見つかったら終了（先勝ち）
        if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
            return


_APPENDIX_BODY_LIMIT = 3   # appendix のみ圧縮対象
_APPENDIX_BULLETS_LIMIT = 5


def _compact_slide(s: dict, compress_appendix: bool) -> dict:
    """スライド1枚を送信用に整形。appendix のみ圧縮、それ以外は全量。"""
    role = s.get("role")
    is_appendix = role in ("appendix", "company-profile", "team-profile") and compress_appendix
    body = s.get("body_paragraphs") or []
    bullets = s.get("bullets") or []
    tables = s.get("tables") or []
    notes = s.get("speaker_notes") or ""
    if is_appendix:
        body = body[:_APPENDIX_BODY_LIMIT]
        bullets = bullets[:_APPENDIX_BULLETS_LIMIT]
        tables = []  # appendix の表は省略
        notes = ""   # appendix のノートは省略
    return {
        "slide": s.get("slide") or s.get("slide_number") or s.get("index"),
        "role": role,
        "hidden": s.get("hidden", False),
        "title": s.get("title"),
        "body_paragraphs": body,
        "bullets": bullets,
        "tables": tables,
        "speaker_notes": notes,
        "has_image": s.get("has_image", False),
        "has_chart": s.get("has_chart", False),
        "has_table": bool(s.get("tables")),
    }


def _build_user_prompt(ai_check_data: dict) -> str:
    """AIチェックJSONを LLM に渡すプロンプトに整形。

    戦略コンサルレベルのレビュー精度を出すため、本文・表・スピーカーノートを
    切り詰めずそのまま渡す。context長対策として appendix/会社概要/経歴 系のみ
    圧縮する。総文字数が一定を超える場合のみ appendix を圧縮するヒューリス
    ティクスを採用。
    """
    slides = ai_check_data.get("slides") or []
    toc = ai_check_data.get("table_of_contents") or []

    # まず全量で組み立て、文字数が大きすぎる場合のみ appendix を圧縮
    full = [_compact_slide(s, compress_appendix=False) for s in slides]
    full_json = json.dumps(full, ensure_ascii=False, indent=2)
    THRESHOLD = 80000  # 文字数。超えたら appendix を圧縮
    if len(full_json) > THRESHOLD:
        compact = [_compact_slide(s, compress_appendix=True) for s in slides]
        slides_payload = json.dumps(compact, ensure_ascii=False, indent=2)
    else:
        slides_payload = full_json

    return (
        "以下は提出前のクライアント提案資料のスライド構造データです。\n"
        "Tier-1 戦略コンサルの MD/Partner として赤入れレベルのレビューを行ってください。\n\n"
        f"# 目次 (table_of_contents)\n{json.dumps(toc, ensure_ascii=False, indent=2)}\n\n"
        f"# スライド本体 (slides)\n{slides_payload}\n\n"
        "上記を 15 観点で網羅レビューし、指示どおりの JSON オブジェクト"
        "（overall_assessment + findings）のみを返してください。"
    )


def _parse_llm_response(text: str) -> dict:
    """LLM応答から JSON オブジェクト（overall_assessment + findings）を抽出。

    旧フォーマット（裸のJSON配列）が返ってきた場合は findings 扱いに包んで
    返し、overall_assessment は空にする。
    """
    # ```json ... ``` を剥がす（オブジェクト/配列どちらも）
    m = re.search(r"```(?:json)?\s*([\{\[].*?[\}\]])\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    text = text.strip()

    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                if "findings" not in data:
                    data["findings"] = []
                if "overall_assessment" not in data:
                    data["overall_assessment"] = {}
                return data
        except json.JSONDecodeError:
            pass

    # 配列だけが返ってきた場合（旧フォーマット互換）
    if not text.startswith("["):
        s = text.find("[")
        e = text.rfind("]")
        if s != -1 and e != -1:
            text = text[s:e + 1]
    try:
        arr = json.loads(text)
        if isinstance(arr, list):
            return {"overall_assessment": {}, "findings": arr}
    except json.JSONDecodeError:
        pass
    return {"overall_assessment": {}, "findings": []}


def _format_finding_note(it: dict) -> str:
    """8フィールドの指摘を1本の note 文字列に整形。"""
    issue = str(it.get("issue", "")).strip()
    why = str(it.get("why_it_matters", "")).strip()
    sug = str(it.get("suggestion", "")).strip()
    rew = str(it.get("rewrite_example", "")).strip()
    parts = [issue]
    if why:
        parts.append(f"影響: {why}")
    if sug:
        parts.append(f"改善案: {sug}")
    if rew:
        parts.append(f"書き換え例: {rew}")
    return " / ".join(p for p in parts if p)


def _format_overall_assessment_note(oa: dict) -> Optional[str]:
    """overall_assessment を 1 件の Finding (location 0, INFO) として表現するための note。"""
    if not oa:
        return None
    parts = []
    if oa.get("estimated_grade"):
        parts.append(f"評価: {oa['estimated_grade']}")
    if oa.get("client_readiness"):
        parts.append(f"提出可否: {oa['client_readiness']}")
    if oa.get("key_question"):
        parts.append(f"Key Question: {oa['key_question']}")
    if oa.get("answer_clarity"):
        parts.append(f"答え明瞭度: {oa['answer_clarity']}")
    if oa.get("partner_one_liner"):
        parts.append(f"Partner一言: {oa['partner_one_liner']}")
    if oa.get("story_line_summary"):
        parts.append(f"ストーリー: {oa['story_line_summary']}")
    strengths = oa.get("top_strengths") or []
    weaknesses = oa.get("top_weaknesses") or []
    if strengths:
        parts.append(f"強み: {' / '.join(strengths)}")
    if weaknesses:
        parts.append(f"弱み: {' / '.join(weaknesses)}")
    return " | ".join(p for p in parts if p) or None


def run_llm_review(
    ai_check_json_path: str,
    model: str = DEFAULT_MODEL,
    env_path: str | None = None,
) -> tuple[List[Finding], Optional[str]]:
    """Gemini に定性レビューを依頼。

    Returns:
        (findings, error_message) — errorがNoneなら成功
    """
    load_env(env_path)
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return [], "GOOGLE_API_KEY (or GEMINI_API_KEY) が環境変数または .env に見つかりません"

    # .env に GOOGLE_GENAI_USE_VERTEXAI=true があると SDK が Vertex AI モードに
    # 切り替わり API キーでは 401 UNAUTHENTICATED になる。この呼び出しでは
    # 明示的に Gemini API モード（vertexai=False）に固定する。
    for var in ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT",
                "GOOGLE_CLOUD_LOCATION", "GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ.pop(var, None)

    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        return [], "google-genai パッケージが未インストール (`pip install google-genai`)"

    try:
        ai_check_data = json.loads(Path(ai_check_json_path).read_text(encoding="utf-8"))
    except Exception as e:
        return [], f"AIチェックJSON読み込み失敗: {e}"

    client = genai.Client(api_key=api_key, vertexai=False)
    user_prompt = _build_user_prompt(ai_check_data)

    try:
        resp = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
    except Exception as e:
        return [], f"Gemini API 呼び出し失敗: {e}"

    text = getattr(resp, "text", "") or ""
    parsed = _parse_llm_response(text)
    items = parsed.get("findings") or []
    overall = parsed.get("overall_assessment") or {}
    if not items and not overall:
        return [], f"LLM応答のJSON解析に失敗。応答先頭: {text[:200]}"

    findings: List[Finding] = []

    # overall_assessment を最上位の総評Findingとして1件出す
    oa_note = _format_overall_assessment_note(overall)
    if oa_note:
        findings.append(Finding(
            checker=CHECKER,
            severity=SEVERITY_INFO,
            category="llm/overall-assessment",
            location_label="(全体)",
            location_index=0,
            evidence=(overall.get("partner_one_liner") or oa_note)[:100],
            note=oa_note,
            source_handle=None,
        ))

    for it in items:
        sev_raw = str(it.get("severity", "INFO")).upper()
        sev = SEV_MAP.get(sev_raw, SEVERITY_INFO)
        cat = str(it.get("category", "quality")).lower()
        slide = it.get("slide", 0)
        try:
            slide_idx = int(slide)
        except (TypeError, ValueError):
            slide_idx = 0
        label = f"Slide {slide_idx}" if slide_idx > 0 else "(全体)"
        quote = str(it.get("quote", "")).strip()
        note = _format_finding_note(it)
        evidence = quote[:100] if quote else str(it.get("issue", ""))[:100]
        findings.append(Finding(
            checker=CHECKER,
            severity=sev,
            category=f"llm/{cat}",
            location_label=label,
            location_index=slide_idx,
            evidence=evidence,
            note=note,
            source_handle=None,
        ))
    return findings, None
