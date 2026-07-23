"""Phase 1 style checks: title messaging, term inconsistency, prohibited
expressions, honorific/plain mixing, date-format mixing.
"""
import re
from collections import defaultdict
from typing import List, Dict

from checkers import Finding, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO


# ============================================================
# 1. Title as message (not体言止め)
# ============================================================

# Pages that don't need a "message" title
_EXCLUDED_TITLE_KEYWORDS = [
    "目次", "アジェンダ", "Agenda", "Contents", "Index",
    "会社概要", "Company", "企業概要",
    "経歴", "Profile", "プロフィール",
    "はじめに", "Introduction",
    "まとめ", "Summary", "Conclusion",
    "Appendix", "参考", "Reference", "補足", "付録",
    "表紙", "Cover", "Title",
    "ご説明資料", "ご提案書", "提案書",
    "ご挨拶",
    "実績", "Case Study", "事例",
]

# Title endings that indicate a message (predicate/verb/assertion)
_MESSAGE_ENDING_PATTERNS = [
    # verbs in dictionary/past/negative form
    re.compile(r"(?:する|した|している|される|された|なる|なった|なっている)[。.]?$"),
    re.compile(r"(?:です|ます|だ|である|でした|ました)[。.]?$"),
    re.compile(r"(?:べき|べく|必要|重要|可能|不可欠|推奨|困難|容易|明確|不明)[。.だ]?$"),
    re.compile(r"(?:検討|確認|実施|提案|分析|整理|構築|強化|改善|向上|低下|拡大|縮小|増加|減少)(?:する|した|が必要|を検討|を提案|を推奨|すべき|中)?[。.]?$"),
    # connectives at end (ongoing logic)
    re.compile(r"(?:が|は|を|に|へ|と|で)[^。]*(?:か|ない|ある|いる|える|られる|できる)[。.]?$"),
    # interrogative / directive
    re.compile(r"[?？!！]$"),
    re.compile(r"(?:とは|について|に関して|に向けて)$"),  # these can be OK (topic marker) — let's treat as message-ish
]


def _is_excluded_title(title: str) -> bool:
    t = title.strip()
    for kw in _EXCLUDED_TITLE_KEYWORDS:
        if kw in t:
            return True
    return False


def _looks_like_message(title: str) -> bool:
    t = title.strip().rstrip("　 ")
    if not t:
        return True  # empty; handled elsewhere
    # short labels like "Chapter 1", "1.", "第1章" are structural
    if re.match(r"^(?:第\s*\d+|Chapter\s*\d+|\d+[.．、]|Section\s*\d+)", t, re.IGNORECASE):
        return True
    for p in _MESSAGE_ENDING_PATTERNS:
        if p.search(t):
            return True
    return False


def check_title_messaging_pptx(doc) -> List[Finding]:
    findings = []
    if doc.ext != ".pptx":
        return findings

    for slide_idx, slide in enumerate(doc.raw.slides, start=1):
        try:
            title_shape = slide.shapes.title
        except Exception:
            title_shape = None
        if not title_shape:
            continue
        title_text = (title_shape.text or "").strip()
        if not title_text:
            continue
        if _is_excluded_title(title_text):
            continue
        if _looks_like_message(title_text):
            continue
        findings.append(Finding(
            checker="consulting-style",
            severity=SEVERITY_LOW,
            category="title-noun-ending",
            location_label=f"Slide {slide_idx}",
            location_index=slide_idx,
            evidence=title_text[:120],
            note="タイトルが体言止めです。「〜する/した/べき/が重要」のようなメッセージ文にすると、So What? が伝わります。",
            source_handle=title_shape,
        ))
    return findings


# ============================================================
# 2. Term inconsistency (表記ゆれ)
# ============================================================

# Each entry is (group_name, [list of variant patterns]). If 2+ variants appear
# anywhere in the document, emit one finding with the inconsistent pair.
_TERM_GROUPS = [
    ("country-us", [r"米国", r"アメリカ", r"\bUSA?\b", r"\bU\.S\.?(?:A\.?)?\b"]),
    ("country-uk", [r"英国", r"イギリス", r"\bUK\b", r"\bU\.K\.?\b"]),
    ("customer", [r"(?<!御)顧客", r"クライアント", r"お客様", r"お客さま"]),
    ("your-company", [r"御社", r"貴社"]),
    ("our-company", [r"(?<!他)当社", r"弊社", r"当方"]),
    ("server", [r"サーバー", r"サーバ(?!ー)"]),
    ("memory", [r"メモリー", r"メモリ(?!ー)"]),
    ("user", [r"ユーザー", r"ユーザ(?!ー)"]),
    ("computer", [r"コンピューター", r"コンピュータ(?!ー)"]),
    ("interface", [r"インターフェース", r"インタフェース", r"インターフェイス"]),
    ("data", [r"データー", r"データ(?!ー)"]),
]


def _full_to_half_digits(text: str) -> int:
    """Count 全角 digits."""
    return len(re.findall(r"[０-９]", text))


def _has_half_digits(text: str) -> int:
    return len(re.findall(r"\d", text))


def _full_to_half_alpha(text: str) -> int:
    return len(re.findall(r"[Ａ-Ｚａ-ｚ]", text))


def _has_half_alpha(text: str) -> int:
    return len(re.findall(r"[A-Za-z]", text))


def check_term_inconsistency(doc) -> List[Finding]:
    findings = []
    all_text = "\n".join(doc.location_text.values())
    # Where each variant first appears
    variant_locations: Dict[str, Dict[str, int]] = {}

    for group_name, variants in _TERM_GROUPS:
        found_variants = {}
        for v in variants:
            # find first location where this variant appears
            for loc_idx, text in doc.location_text.items():
                if re.search(v, text):
                    # Use a representative match string for display
                    m = re.search(v, text)
                    found_variants[v] = (loc_idx, m.group(0))
                    break
        if len(found_variants) >= 2:
            parts = [f"`{m[1]}`(@{doc.location_flags.get(m[0], {}).get('label', m[0])})"
                     for m in found_variants.values()]
            # Fire on the location of the first appearance
            first_loc = min(m[0] for m in found_variants.values())
            label = doc.location_flags.get(first_loc, {}).get("label", f"Loc {first_loc}")
            findings.append(Finding(
                checker="consulting-style",
                severity=SEVERITY_MEDIUM,
                category=f"term-inconsistency/{group_name}",
                location_label=label,
                location_index=first_loc,
                evidence=" / ".join(parts),
                note="同一資料内で表記が揺れています。統一を検討してください。",
            ))

    # Full/half-width digit mixing
    full_digits = _full_to_half_digits(all_text)
    half_digits = _has_half_digits(all_text)
    if full_digits > 0 and half_digits > 0 and full_digits >= 3:
        findings.append(Finding(
            checker="consulting-style",
            severity=SEVERITY_LOW,
            category="term-inconsistency/digit-width",
            location_label="File",
            location_index=0,
            evidence=f"全角数字 {full_digits}件 / 半角数字 {half_digits}件",
            note="全角数字と半角数字が混在しています。半角に統一するのが一般的です。",
        ))

    # Full/half-width Latin alpha mixing
    full_alpha = _full_to_half_alpha(all_text)
    half_alpha = _has_half_alpha(all_text)
    if full_alpha > 0 and half_alpha > 0 and full_alpha >= 3:
        findings.append(Finding(
            checker="consulting-style",
            severity=SEVERITY_LOW,
            category="term-inconsistency/alpha-width",
            location_label="File",
            location_index=0,
            evidence=f"全角英字 {full_alpha}件 / 半角英字 {half_alpha}件",
            note="全角英字と半角英字が混在しています。半角に統一するのが一般的です。",
        ))

    return findings


# ============================================================
# 3. Prohibited / risky expressions
# ============================================================

_KEIHYO_PATTERNS = [
    (re.compile(r"(?<![\w.])No\.?\s*1(?![\d])", re.IGNORECASE), "No.1"),
    (re.compile(r"業界\s*(?:No\.?\s*1|ナンバーワン|トップ)", re.IGNORECASE), "業界No.1"),
    (re.compile(r"(?:世界|日本|国内|業界)(?:一|最高|最大|最良|最強|最先端|唯一)"), "最上級表現"),
    (re.compile(r"(?:絶対|100\s*%|百%)(?:確実|安全|成功|保証)"), "絶対保証"),
    (re.compile(r"必ず(?:成功|達成|実現|保証|なる)"), "必ず保証"),
    (re.compile(r"(?:他社|競合)(?:にはない|を圧倒|を凌駕)"), "他社排他"),
]

_VAGUE_PATTERNS = [
    re.compile(r"(?:と思われる|と思います|と考えられる)"),
    re.compile(r"(?:のようだ|のようです|のような気がする)"),
    re.compile(r"(?:かもしれない|かもしれません)"),
    re.compile(r"(?:おそらく|たぶん|多分)"),
    re.compile(r"(?:〜?など|〜?等)"),
    re.compile(r"(?:的な|的に)"),
    re.compile(r"(?:様々な|いろいろな|色々な)"),
]


def check_prohibited_expressions(doc) -> List[Finding]:
    findings = []
    # Keihyo-ho (景表法) risks: flag each occurrence as MEDIUM
    for u in doc.units:
        for p, label in _KEIHYO_PATTERNS:
            for m in p.finditer(u.text):
                findings.append(Finding(
                    checker="consulting-style",
                    severity=SEVERITY_MEDIUM,
                    category="prohibited/keihyo-risk",
                    location_label=u.location_label,
                    location_index=u.location_index,
                    evidence=f"{label}: {m.group(0)}",
                    note="景表法リスク表現。合理的根拠の提示が必要。断定を避けた表現に言い換えを検討してください。",
                    source_handle=u.source_handle,
                ))

    # Vague expressions: count per location, flag if 3+
    for loc_idx, text in doc.location_text.items():
        hits = []
        for p in _VAGUE_PATTERNS:
            hits.extend(p.findall(text))
        if len(hits) >= 3:
            label = doc.location_flags.get(loc_idx, {}).get("label", f"Loc {loc_idx}")
            findings.append(Finding(
                checker="consulting-style",
                severity=SEVERITY_INFO,
                category="prohibited/vague-overuse",
                location_label=label,
                location_index=loc_idx,
                evidence=f"{len(hits)}件: {', '.join(set(hits))[:120]}",
                note="曖昧表現（〜と思われる/など/的な等）が多用されています。断定を検討してください。",
            ))
    return findings


# ============================================================
# 4. Honorific/plain mixing (敬体/常体混在)
# ============================================================

_KEITAI_RE = re.compile(r"(?:です|ます|ました|ません|でしょう|でした|しましょう)(?:[。！？、]|$)")
_JYOUTAI_RE = re.compile(r"(?:だ|である|でない|だった|であった|ではない|ではなかった)(?:[。！？、]|$)")


def check_honorific_mixing(doc) -> List[Finding]:
    findings = []
    for loc_idx, text in doc.location_text.items():
        keitai = len(_KEITAI_RE.findall(text))
        jyoutai = len(_JYOUTAI_RE.findall(text))
        if keitai >= 1 and jyoutai >= 1:
            label = doc.location_flags.get(loc_idx, {}).get("label", f"Loc {loc_idx}")
            findings.append(Finding(
                checker="consulting-style",
                severity=SEVERITY_LOW,
                category="honorific-plain-mixing",
                location_label=label,
                location_index=loc_idx,
                evidence=f"敬体 {keitai}件 / 常体 {jyoutai}件",
                note="敬体（です/ます）と常体（だ/である）が混在しています。資料全体で統一を検討してください。",
            ))
    return findings


# ============================================================
# 5. Date-format mixing
# ============================================================

_DATE_FMT_PATTERNS = [
    ("slash-ymd",    re.compile(r"\b(?:19|20)\d{2}/\d{1,2}/\d{1,2}\b")),
    ("hyphen-ymd",   re.compile(r"\b(?:19|20)\d{2}-\d{1,2}-\d{1,2}\b")),
    ("ja-ymd",       re.compile(r"(?:19|20)\d{2}年\s*\d{1,2}月\s*\d{1,2}日")),
    ("reiwa-ymd",    re.compile(r"令和\s*\d{1,2}年\s*\d{1,2}月(?:\s*\d{1,2}日)?")),
    ("us-mdy",       re.compile(r"\b\d{1,2}/\d{1,2}/(?:19|20)\d{2}\b")),
    ("eng-full",     re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(?:19|20)\d{2}\b", re.IGNORECASE)),
]


def check_date_format_mixing(doc) -> List[Finding]:
    all_text = "\n".join(doc.location_text.values())
    present = {}
    for name, p in _DATE_FMT_PATTERNS:
        m = p.search(all_text)
        if m:
            # Find the first location it appears in
            for loc_idx, text in doc.location_text.items():
                if p.search(text):
                    present[name] = (loc_idx, m.group(0))
                    break
    if len(present) >= 2:
        first_loc = min(v[0] for v in present.values())
        label = doc.location_flags.get(first_loc, {}).get("label", f"Loc {first_loc}")
        parts = [f"{name}=`{sample}`" for name, (_, sample) in present.items()]
        return [Finding(
            checker="consulting-style",
            severity=SEVERITY_LOW,
            category="date-format-mixing",
            location_label=label,
            location_index=first_loc,
            evidence=" / ".join(parts),
            note=f"日付書式が {len(present)} 種類混在しています。統一を検討してください。",
        )]
    return []


# ============================================================
# Entry
# ============================================================

def run_style_checks(doc) -> List[Finding]:
    findings = []
    findings.extend(check_title_messaging_pptx(doc))
    findings.extend(check_term_inconsistency(doc))
    findings.extend(check_prohibited_expressions(doc))
    findings.extend(check_honorific_mixing(doc))
    findings.extend(check_date_format_mixing(doc))
    return findings
