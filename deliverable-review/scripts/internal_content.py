"""Extract speaker notes, hidden slides, and comments — internal content that
may accidentally reach the client. Flags entries that contain 'danger words'
suggesting the content was never meant to be shared.
"""
import re
import zipfile
from typing import List
from xml.etree import ElementTree as ET

from checkers import Finding, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO


# Words that clearly mean "don't show this to client" → HIGH
_DANGER_PATTERNS = [
    re.compile(r"(?:クライアント|顧客|先方|お客様?)に(?:は)?(?:言わない|伝えない|見せない|触れない|共有しない)"),
    re.compile(r"(?:ここ|これ|この話|この件)は(?:内輪|社内|オフレコ|NG|伏せ)"),
    re.compile(r"(?:社内|内部)(?:限り|のみ|用|向け|マター)"),
    re.compile(r"オフレコ"),
    re.compile(r"伏せ(?:て|る|ます)"),
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bFIXME\b", re.IGNORECASE),
    re.compile(r"\bXXX\b"),
    re.compile(r"\bconfidential\b", re.IGNORECASE),
    re.compile(r"\binternal\s+only\b", re.IGNORECASE),
    re.compile(r"\bdo not share\b", re.IGNORECASE),
    re.compile(r"(?:competitor|ライバル|他社|競合).{0,10}(?:の話|には)"),
]

# Words that merely deserve a look (common in legitimate notes) → MEDIUM
_CAUTION_PATTERNS = [
    re.compile(r"(?:暫定|未確定|検討中|要確認|確認中|仮置き|仮値|仮の(?:数字|数値|値))"),
    re.compile(r"(?:値引き|ディスカウント|赤字|原価|利益率|マージン|採算)"),
    re.compile(r"(?:スルー|スキップ)"),
    re.compile(r"\bNOTE[:：]"),
    re.compile(r"\binternal\b", re.IGNORECASE),
    re.compile(r"\bdraft\b", re.IGNORECASE),
]


def _hits(patterns, text: str) -> List[str]:
    return [m.group(0) for p in patterns for m in p.finditer(text)]


def _has_danger(text: str) -> List[str]:
    return _hits(_DANGER_PATTERNS, text)


def _has_caution(text: str) -> List[str]:
    return _hits(_CAUTION_PATTERNS, text)


def _grade(text: str, base: str):
    """Return (severity, note_suffix) for internal text."""
    danger = _has_danger(text)
    if danger:
        return SEVERITY_HIGH, f" 危険ワード検出: {', '.join(sorted(set(danger)))[:100]}"
    caution = _has_caution(text)
    if caution:
        return SEVERITY_MEDIUM, f" 要注意ワード: {', '.join(sorted(set(caution)))[:100]}"
    return base, ""


# ------------------------------------------------------------
# PPTX: speaker notes, hidden slides, comments
# ------------------------------------------------------------

def _pptx_speaker_notes(doc) -> List[Finding]:
    findings = []
    for slide_idx, slide in enumerate(doc.raw.slides, start=1):
        if not slide.has_notes_slide:
            continue
        note_tf = slide.notes_slide.notes_text_frame
        note_text = (note_tf.text or "").strip()
        if not note_text:
            continue
        sev, suffix = _grade(note_text, SEVERITY_INFO)
        evidence = note_text[:300] + ("…" if len(note_text) > 300 else "")
        note = "スピーカーノートが含まれています。" + suffix
        findings.append(Finding(
            checker="internal-content",
            severity=sev,
            category="speaker-note",
            location_label=f"Slide {slide_idx}",
            location_index=slide_idx,
            evidence=evidence,
            note=note,
        ))
    return findings


def _pptx_hidden_slides(doc) -> List[Finding]:
    findings = []
    for slide_idx, slide in enumerate(doc.raw.slides, start=1):
        try:
            if slide.element.get("show") == "0":
                # Extract title if any
                title = ""
                try:
                    if slide.shapes.title:
                        title = slide.shapes.title.text[:80]
                except Exception:
                    pass
                findings.append(Finding(
                    checker="internal-content",
                    severity=SEVERITY_HIGH,
                    category="hidden-slide",
                    location_label=f"Slide {slide_idx}",
                    location_index=slide_idx,
                    evidence=title or "(no title)",
                    note="非表示スライド。削除するか、意図的なら確認してください。",
                ))
        except Exception:
            pass
    return findings


def _localname(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _pptx_comment_authors(path: str) -> dict:
    """authorId -> name from legacy ppt/commentAuthors.xml and modern ppt/authors.xml."""
    authors = {}
    try:
        with zipfile.ZipFile(path) as z:
            for part in ("ppt/commentAuthors.xml", "ppt/authors.xml"):
                if part not in z.namelist():
                    continue
                root = ET.fromstring(z.read(part))
                for a in root:
                    if _localname(a.tag) in ("cmAuthor", "author"):
                        authors[a.get("id", "")] = a.get("name", "") or a.get("initials", "")
    except Exception:
        pass
    return authors


def _pptx_comments(doc) -> List[Finding]:
    """Legacy (ppt/comments/commentN.xml) and modern (modernComment_*.xml)
    comments, mapped to slides via each slide's relationships — the N in
    commentN.xml is NOT the slide number."""
    findings = []
    authors = _pptx_comment_authors(doc.path)
    for slide_idx, slide in enumerate(doc.raw.slides, start=1):
        for rel in slide.part.rels.values():
            if rel.is_external or not rel.reltype.endswith("/comments"):
                continue
            try:
                root = ET.fromstring(rel.target_part.blob)
            except Exception:
                continue
            for c in root.iter():
                if _localname(c.tag) != "cm":
                    continue
                aid = c.get("authorId", "")
                author = authors.get(aid, aid)
                date = c.get("dt", "") or c.get("created", "")
                text = "".join(
                    (t.text or "") for t in c.iter() if _localname(t.tag) in ("text", "t")
                )
                sev, suffix = _grade(text, SEVERITY_MEDIUM)
                findings.append(Finding(
                    checker="internal-content",
                    severity=sev,
                    category="pptx-comment",
                    location_label=f"Slide {slide_idx}",
                    location_index=slide_idx,
                    evidence=f"[{author} {date}] {text[:200]}",
                    note="PPTコメントが残っています。--sanitize で削除可能。" + suffix,
                ))
    return findings


# ------------------------------------------------------------
# DOCX: comments, tracked changes presence
# ------------------------------------------------------------

def _docx_comments(doc) -> List[Finding]:
    findings = []
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        with zipfile.ZipFile(doc.path) as z:
            if "word/comments.xml" not in z.namelist():
                return findings
            try:
                root = ET.fromstring(z.read("word/comments.xml"))
            except Exception:
                return findings
            for c in root.findall("w:comment", ns):
                author = c.get(f"{{{ns['w']}}}author", "")
                date = c.get(f"{{{ns['w']}}}date", "")
                # Flatten text
                parts = []
                for t in c.iter(f"{{{ns['w']}}}t"):
                    if t.text:
                        parts.append(t.text)
                text = "".join(parts)
                sev, suffix = _grade(text, SEVERITY_MEDIUM)
                findings.append(Finding(
                    checker="internal-content",
                    severity=sev,
                    category="docx-comment",
                    location_label="Document",
                    location_index=0,
                    evidence=f"[{author} {date}] {text[:200]}",
                    note="Wordコメントが残っています。--sanitize で削除可能。" + suffix,
                ))
    except Exception:
        pass
    return findings


# ------------------------------------------------------------
# Entry
# ------------------------------------------------------------

def run_internal_content(doc) -> List[Finding]:
    findings = []
    if doc.ext == ".pptx":
        findings.extend(_pptx_speaker_notes(doc))
        findings.extend(_pptx_hidden_slides(doc))
        findings.extend(_pptx_comments(doc))
    elif doc.ext == ".docx":
        findings.extend(_docx_comments(doc))
    # PDF: no speaker notes / hidden slides / comments in standard PDFs
    return findings
