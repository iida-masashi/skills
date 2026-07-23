"""Detection patterns for deliverable-review skill.

All regex patterns use re.IGNORECASE unless otherwise noted.
"""
import re

# ============================================================
# URL contamination patterns
# ============================================================

# AI tool origin markers in query strings (utm_source, ref, etc.)
_AI_TOOLS = [
    "chatgpt", "chatgpt.com", "openai", "openai.com",
    "claude", "claude.ai", "anthropic", "anthropic.com",
    "perplexity", "perplexity.ai",
    "gemini", "bard", "google-gemini", "gemini.google.com",
    "copilot", "bing-chat", "microsoft-copilot", "bingchat",
    "grok", "grok.x.ai", "you.com", "phind", "poe.com",
    "kimi", "deepseek", "mistral",
]

URL_AI_QUERY_PATTERNS = [
    # utm_source=chatgpt.com, utm_medium=claude, utm_campaign=perplexity等
    re.compile(
        r"[?&](?:utm_source|utm_medium|utm_campaign|utm_content|utm_term|ref|ref_src|source)"
        r"=(?:" + "|".join(re.escape(t) for t in _AI_TOOLS) + r")\b",
        re.IGNORECASE,
    ),
]

# AI tool conversation/share URLs (should never appear in client deliverables)
URL_AI_DOMAIN_PATTERNS = [
    re.compile(r"https?://chat\.openai\.com/[\w\-/?=&#.]+", re.IGNORECASE),
    re.compile(r"https?://chatgpt\.com/(?:c|share|g)/[\w\-/?=&#.]+", re.IGNORECASE),
    re.compile(r"https?://claude\.ai/(?:chat|share|project)/[\w\-/?=&#.]+", re.IGNORECASE),
    re.compile(r"https?://gemini\.google\.com/(?:app|share)/[\w\-/?=&#.]+", re.IGNORECASE),
    re.compile(r"https?://(?:www\.)?perplexity\.ai/(?:search|page)/[\w\-/?=&#.]+", re.IGNORECASE),
    re.compile(r"https?://copilot\.microsoft\.com/[\w\-/?=&#.]+", re.IGNORECASE),
    re.compile(r"https?://poe\.com/(?:s|chat)/[\w\-/?=&#.]+", re.IGNORECASE),
]

# General tracking parameters (inappropriate for consulting deliverables)
URL_GENERAL_TRACKING_PATTERNS = [
    re.compile(r"[?&](?:fbclid|gclid|msclkid|yclid|dclid)=[^&\s]+", re.IGNORECASE),
    re.compile(r"[?&](?:mc_cid|mc_eid)=[^&\s]+", re.IGNORECASE),
    re.compile(r"[?&]_ga=[^&\s]+", re.IGNORECASE),
    re.compile(r"[?&]_gl=[^&\s]+", re.IGNORECASE),
    re.compile(r"[?&]igshid=[^&\s]+", re.IGNORECASE),
    re.compile(r"[?&](?:hsa_[a-z]+|hsCtaTracking)=[^&\s]+", re.IGNORECASE),  # HubSpot
    re.compile(r"[?&]vero_(?:id|conv)=[^&\s]+", re.IGNORECASE),
    re.compile(r"[?&]s_cid=[^&\s]+", re.IGNORECASE),  # Adobe
]

# Generic URL extraction (for URL liveness check)
URL_GENERIC_PATTERN = re.compile(
    r"https?://[^\s<>\"'\)\]\}、。]+",
    re.IGNORECASE,
)


def find_url_contamination(text: str):
    """Return list of (category, matched_string) tuples."""
    findings = []
    for p in URL_AI_QUERY_PATTERNS:
        for m in p.finditer(text):
            findings.append(("AI-origin-query-param", m.group(0)))
    for p in URL_AI_DOMAIN_PATTERNS:
        for m in p.finditer(text):
            findings.append(("AI-tool-conversation-url", m.group(0)))
    for p in URL_GENERAL_TRACKING_PATTERNS:
        for m in p.finditer(text):
            findings.append(("general-tracking-param", m.group(0)))
    return findings


def extract_all_urls(text: str):
    return [m.group(0).rstrip(".,;:)]}、。") for m in URL_GENERIC_PATTERN.finditer(text)]


# ============================================================
# AI generation trace patterns
# ============================================================

AI_PHRASE_PATTERNS_JA = [
    re.compile(r"申し訳(?:ございません|ありません)が[、,]?\s*(?:AI|私は|言語モデル)"),
    re.compile(r"(?:AIアシスタント|AI|言語モデル)として(?:は|、|,)"),
    re.compile(r"(?:私|I)は(?:AI|言語モデル|人工知能)で(?:す|あり)"),
    re.compile(r"ご質問(?:いただき)?ありがとうございます"),
    re.compile(r"お答え(?:いたし)?します[。.:]"),
    re.compile(r"以下(?:に|で)(?:、)?(?:.{0,10})(?:を(?:示|ご説明|解説|まとめ)|について)"),
    re.compile(r"要点を(?:まとめる|整理する)と"),
    re.compile(r"総括(?:する|いたします)と"),
    re.compile(r"(?:結論|まとめ)(?:として|から申し上げる)と"),
    re.compile(r"^※?\s*(?:なお|ちなみに)、本回答は"),
]

AI_PHRASE_PATTERNS_EN = [
    re.compile(r"\bAs an AI\b", re.IGNORECASE),
    re.compile(r"\bAs a language model\b", re.IGNORECASE),
    re.compile(r"\bI'?m an AI\b", re.IGNORECASE),
    re.compile(r"\bI apologize,?\s*but\b", re.IGNORECASE),
    re.compile(r"\bI cannot (?:provide|generate|assist)\b", re.IGNORECASE),
    re.compile(r"\bI don'?t have (?:access to|the ability)\b", re.IGNORECASE),
    re.compile(r"\bCertainly!", re.IGNORECASE),
    re.compile(r"\bI'?d be happy to\b", re.IGNORECASE),
    re.compile(r"\bHere'?s (?:a|an|the) (?:brief|detailed|comprehensive)\b", re.IGNORECASE),
]

# Knowledge cutoff references
AI_CUTOFF_PATTERNS = [
    re.compile(r"(?:20\d{2})年\s*\d{1,2}\s*月(?:時点|現在|まで)(?:の(?:情報|データ|知識))?"),
    re.compile(r"(?:私の)?(?:知識|学習データ|トレーニングデータ)(?:は|の)(?:20\d{2})"),
    re.compile(r"\bas of (?:my (?:last|knowledge) )?(?:update|cutoff|training)\b", re.IGNORECASE),
    re.compile(r"\bknowledge cut[- ]?off\b", re.IGNORECASE),
    re.compile(r"\bmy training data\b", re.IGNORECASE),
    re.compile(r"\bup to (?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}\b", re.IGNORECASE),
]

# Markdown remnants that are unambiguous (rare to appear in a legitimately
# authored PowerPoint / Word document).
AI_MARKDOWN_REMNANT_PATTERNS = [
    re.compile(r"\*\*[^*\n]{1,80}\*\*"),                    # **bold**
    re.compile(r"(?<![\w`])`[^`\n]{1,80}`(?![\w`])"),       # `code`
    re.compile(r"^#{1,6}\s+\S", re.MULTILINE),              # # heading
    re.compile(r"\[[^\]\n]{1,60}\]\(https?://[^)\s]+\)"),   # [text](url)
]

# Ambiguous bullet patterns — `- X` or `1. X` at the start of a line.
# In PowerPoint the native bullet character sometimes surfaces as a literal
# "- " prefix in extracted text, which isn't a Markdown remnant but just a
# rendering artifact. We only flag these when MULTIPLE bullet lines appear
# in the SAME paragraph — a single "- X" is almost always a native bullet.
_BULLET_LINE_RE = re.compile(r"(?:^|\n)\s*(?:[-*]|\d+\.)\s+\S")

# Excessive emoji use
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "☀-➿"
    "]",
    re.UNICODE,
)


def find_ai_traces(text: str):
    """Return list of (category, matched_string) tuples."""
    findings = []
    for p in AI_PHRASE_PATTERNS_JA:
        for m in p.finditer(text):
            findings.append(("AI-phrase-ja", m.group(0)))
    for p in AI_PHRASE_PATTERNS_EN:
        for m in p.finditer(text):
            findings.append(("AI-phrase-en", m.group(0)))
    for p in AI_CUTOFF_PATTERNS:
        for m in p.finditer(text):
            findings.append(("knowledge-cutoff-mention", m.group(0)))
    for p in AI_MARKDOWN_REMNANT_PATTERNS:
        for m in p.finditer(text):
            findings.append(("markdown-remnant", m.group(0)))
    # Only flag bullet remnants when MULTIPLE bullet lines appear in the same
    # text unit — a single "- X" is typically a native bullet rendering, not
    # a Markdown remnant.
    bullet_matches = _BULLET_LINE_RE.findall(text)
    if len(bullet_matches) >= 2:
        findings.append(("markdown-remnant-bullets",
                         f"{len(bullet_matches)} bullet lines in same paragraph"))
    emojis = _EMOJI_RE.findall(text)
    if len(emojis) >= 3:
        findings.append(("excessive-emoji", f"{len(emojis)} emojis: {''.join(emojis[:10])}"))
    return findings


# ============================================================
# Citation / source markers (presence indicates "has source")
# ============================================================

CITATION_MARKERS_RE = re.compile(
    r"(?:"
    r"出典|出所|参考(?:文献|資料|URL)?|引用(?:元)?|参照|ソース|引用元|典拠|根拠|"
    r"\bSource[s]?\b|\bReference[s]?\b|\bCitation[s]?\b|\bSee\b|\bRef\.?\b|\bvia\b|"
    r"©|Ⓒ|\(c\)|Copyright|All rights reserved|無断転載|著作権"
    r")",
    re.IGNORECASE,
)

# Also treat presence of a URL as evidence of a source
HAS_URL_RE = re.compile(r"https?://\S+")


def has_citation(text: str) -> bool:
    return bool(CITATION_MARKERS_RE.search(text)) or bool(HAS_URL_RE.search(text))


# ============================================================
# Verifiable claims: numbers, proper nouns, dates
# ============================================================

# Numbers with units (percentages, currency, big numbers)
CLAIM_NUMBER_PATTERNS = [
    re.compile(r"\d+(?:\.\d+)?\s*[%％]"),
    re.compile(r"\d+(?:\.\d+)?\s*(?:倍|割|ポイント|pt|bps)"),
    re.compile(r"(?:約|およそ)?\s*\d{1,3}(?:[,，]\d{3})+\s*(?:円|ドル|USD|JPY|EUR|元)"),
    re.compile(r"\d+(?:\.\d+)?\s*(?:兆|億|万|千万|百万|千)\s*(?:円|ドル|USD|JPY|EUR|元|人|件|社)"),
    re.compile(r"(?:CAGR|年率|年平均)\s*[:：]?\s*\d+(?:\.\d+)?\s*[%％]", re.IGNORECASE),
    re.compile(r"\$\s?\d+(?:[.,]\d+)*\s*(?:billion|million|trillion|B|M|T)\b", re.IGNORECASE),
]

# Dates (specific enough to verify)
CLAIM_DATE_PATTERNS = [
    re.compile(r"(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?"),
    re.compile(r"(?:19|20)\d{2}\s*年度?"),
    re.compile(r"\b(?:19|20)\d{2}[-/]\d{1,2}(?:[-/]\d{1,2})?\b"),
    re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(?:19|20)\d{2}\b", re.IGNORECASE),
    re.compile(r"(?:第\s*\d+\s*四半期|Q[1-4]\s*(?:19|20)\d{2})"),
]

# Proper-noun-ish claims: ranking + entity (e.g. "世界第N位", "業界シェアN位")
# Only match when a concrete number/quantity is co-located; bare mentions like
# "売上高", "売上成長率" aren't verifiable claims on their own.
CLAIM_RANKING_PATTERNS = [
    re.compile(r"(?:世界|国内|業界|市場)(?:第)?\s*\d+\s*位"),
    re.compile(r"(?:シェア|占有率)\s*\d+(?:\.\d+)?\s*[%％]"),
    re.compile(
        r"(?:売上高?|売上高|時価総額|従業員数|営業利益|純利益|資本金)"
        r"(?:\s*[:：はがの])?\s*"
        r"(?:約|およそ)?\s*"
        r"\d+(?:[.,]\d+)*\s*"
        r"(?:兆|億|万|千万|百万|千)?\s*"
        r"(?:円|ドル|USD|JPY|EUR|元|人|件|社|%|％)"
    ),
    re.compile(r"\btop\s*\d+\b", re.IGNORECASE),
]


def extract_verifiable_claims(text: str):
    """Return list of (category, matched_string) tuples."""
    claims = []
    for p in CLAIM_NUMBER_PATTERNS:
        for m in p.finditer(text):
            claims.append(("number", m.group(0)))
    for p in CLAIM_DATE_PATTERNS:
        for m in p.finditer(text):
            claims.append(("date", m.group(0)))
    for p in CLAIM_RANKING_PATTERNS:
        for m in p.finditer(text):
            claims.append(("ranking-or-stat", m.group(0)))
    return claims


# ============================================================
# Copyright long-text threshold
# ============================================================

LONG_TEXT_THRESHOLD = 100  # characters
