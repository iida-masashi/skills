"""Extract speaker notes, hidden slides, and comments — internal content that
may accidentally reach the client. Flags entries that contain 'danger words'
suggesting the content was never meant to be shared.
"""
import re
import zipfile
from typing import List
from xml.etree import ElementTree as ET

from checkers import Finding, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO


# Words that suggest "don't show this to client"
_DANGER_PATTERNS = [
    re.compile(r"(?:クライアント|顧客|先方|お客様?)に(?:は)?(?:言わない|伝えない|見せない|触れない|共有しない)"),
    re.compile(r"(?:ここ|これ|この話|この件)は(?:内輪|社内|オフレコ|NG|伏せ)"),
    re.compile(r"(?:社内|内部)(?:限り|のみ|用|向け|マター)"),
    re.compile(r"オフレコ"),
    re.compile(r"伏せ(?:て|る|ます)"),
    re.compile(r"(?:避ける|スルー|スキップ)"),
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bFIXME\b", re.IGNORECASE),
    re.compile(r"\bXXX\b"),
    re.compile(r"\bNOTE[:：]"),
    re.compile(r"\bconfidential\b", re.IGNORECASE),
    re.compile(r"\binternal(?:\s+only)?\b", re.IGNORECASE),
    re.compile(r"\bdo not share\b", re.IGNORECASE),
    re.compile(r"\bdraft\b", re.IGNORECASE),
    re.compile(r"(?:仮|暫定|未確定|検討中|要確認|確認中)"),
    re.compile(r"(?:値引き|ディスカウント|赤字|原価|利益率|マージン|採算)"),
    re.compile(r"(?:competitor|ライバル|他社|競合).{0,10}(?:の話|には)"),
]


def _has_danger(text: str) -> List[str]:
    hits = []
    for p in _DANGER_PATTERNS:
        for m in p.finditer(text):
            hits.append(m.group(0))
    return hits


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
        danger = _has_danger(note_text)
        sev = SEVERITY_HIGH if danger else SEVERITY_INFO
        evidence = note_text[:300] + ("…" if len(note_text) > 300 else "")
        note = "スピーカーノートが含まれています。"
        if danger:
            note += f" 危険ワード検出: {', '.join(set(danger))[:100]}"
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


def _pptx_comments(doc) -> List[Finding]:
    """PPT comments live under ppt/comments/commentN.xml + ppt/commentAuthors.xml"""
    findings = []
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    try:
        with zipfile.ZipFile(doc.path) as z:
            names = z.namelist()
            # Build authorId -> name map
            authors = {}
            if "ppt/commentAuthors.xml" in names:
                try:
                    root = ET.fromstring(z.read("ppt/commentAuthors.xml"))
                    for a in root.findall("p:cmAuthor", ns):
                        aid = a.get("id", "")
                        name = a.get("name", "") or a.get("initials", "")
                        authors[aid] = name
                except Exception:
                    pass
            # Iterate comment files
            for n in names:
                m = re.match(r"ppt/comments/comment(\d+)\.xml", n)
                if not m:
                    continue
                slide_idx = int(m.group(1))
                try:
                    root = ET.fromstring(z.read(n))
                except Exception:
                    continue
                for c in root.findall("p:cm", ns):
                    aid = c.get("authorId", "")
                    author = authors.get(aid, aid)
                    date = c.get("dt", "")
                    text_el = c.find("p:text", ns)
                    text = text_el.text if text_el is not None and text_el.text else ""
                    danger = _has_danger(text)
                    sev = SEVERITY_HIGH if danger else SEVERITY_MEDIUM
                    findings.append(Finding(
                        checker="internal-content",
                        severity=sev,
                        category="pptx-comment",
                        location_label=f"Slide {slide_idx}",
                        location_index=slide_idx,
                        evidence=f"[{author} {date}] {text[:200]}",
                        note="PPTコメントが残っています。削除してください。" + (
                            f" 危険ワード: {', '.join(set(danger))[:80]}" if danger else ""
                        ),
                    ))
    except Exception:
        pass
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
                danger = _has_danger(text)
                sev = SEVERITY_HIGH if danger else SEVERITY_MEDIUM
                findings.append(Finding(
                    checker="internal-content",
                    severity=sev,
                    category="docx-comment",
                    location_label="Document",
                    location_index=1,
                    evidence=f"[{author} {date}] {text[:200]}",
                    note="Wordコメントが残っています。削除してください。" + (
                        f" 危険ワード: {', '.join(set(danger))[:80]}" if danger else ""
                    ),
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
