"""Metadata inspection and sanitization for .pptx / .docx / .pdf.

Detection: always enumerate what's present (author, company, revisions, etc.).
Sanitization (--sanitize flag): writes a <stem>_sanitized.<ext> with sensitive
metadata removed. By default deletes: core/app properties, revision counts,
document comments, and Word track-changes / comments.xml. Hidden slides and
speaker notes are *reported only* (not deleted) since they may be intentional.
"""
import shutil
import zipfile
import re
from pathlib import Path
from typing import List

from checkers import Finding, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO


# ------------------------------------------------------------
# PPTX metadata detect
# ------------------------------------------------------------

def check_metadata_pptx(doc) -> List[Finding]:
    findings = []
    prs = doc.raw
    cp = prs.core_properties
    # Core properties that commonly leak identity
    for attr, label in [
        ("author", "作成者"),
        ("last_modified_by", "最終更新者"),
        ("keywords", "キーワード"),
        ("comments", "コメント(プロパティ)"),
        ("category", "カテゴリ"),
        ("subject", "題目"),
        ("title", "タイトル"),
    ]:
        val = getattr(cp, attr, None)
        if val:
            sev = SEVERITY_HIGH if attr in ("author", "last_modified_by", "comments") else SEVERITY_MEDIUM
            findings.append(Finding(
                checker="metadata",
                severity=sev,
                category=f"core-{attr}",
                location_label="File properties",
                location_index=0,
                evidence=f"{label}: {val}",
                note="ファイルプロパティに識別情報が残っています。--sanitize で削除可能。",
            ))

    # Hidden slides (report only)
    for slide_idx, slide in enumerate(prs.slides, start=1):
        try:
            show = slide.element.get("show")
            if show == "0":
                findings.append(Finding(
                    checker="metadata",
                    severity=SEVERITY_HIGH,
                    category="hidden-slide",
                    location_label=f"Slide {slide_idx}",
                    location_index=slide_idx,
                    evidence="(hidden slide)",
                    note="非表示スライドが含まれています。意図的でなければ削除してください。",
                ))
        except Exception:
            pass

    return findings


# ------------------------------------------------------------
# DOCX metadata detect
# ------------------------------------------------------------

def check_metadata_docx(doc) -> List[Finding]:
    findings = []
    d = doc.raw
    cp = d.core_properties
    for attr, label in [
        ("author", "作成者"),
        ("last_modified_by", "最終更新者"),
        ("keywords", "キーワード"),
        ("comments", "コメント(プロパティ)"),
        ("category", "カテゴリ"),
        ("subject", "題目"),
        ("title", "タイトル"),
    ]:
        val = getattr(cp, attr, None)
        if val:
            sev = SEVERITY_HIGH if attr in ("author", "last_modified_by", "comments") else SEVERITY_MEDIUM
            findings.append(Finding(
                checker="metadata",
                severity=sev,
                category=f"core-{attr}",
                location_label="File properties",
                location_index=0,
                evidence=f"{label}: {val}",
                note="ファイルプロパティに識別情報が残っています。--sanitize で削除可能。",
            ))

    # Track-changes / comments detection via raw zip
    try:
        with zipfile.ZipFile(doc.path) as z:
            names = z.namelist()
            if "word/comments.xml" in names:
                findings.append(Finding(
                    checker="metadata",
                    severity=SEVERITY_HIGH,
                    category="docx-comments",
                    location_label="File",
                    location_index=0,
                    evidence="word/comments.xml present",
                    note="Wordコメントが含まれています。--sanitize で削除可能。",
                ))
            # Detect tracked revisions inside document.xml
            try:
                doc_xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
                if re.search(r"<w:(ins|del)\b", doc_xml):
                    findings.append(Finding(
                        checker="metadata",
                        severity=SEVERITY_HIGH,
                        category="docx-tracked-changes",
                        location_label="File",
                        location_index=0,
                        evidence="tracked changes present",
                        note="変更履歴(Track Changes)が残っています。--sanitize で受け入れ削除します。",
                    ))
            except KeyError:
                pass
    except Exception:
        pass

    return findings


# ------------------------------------------------------------
# PDF metadata detect
# ------------------------------------------------------------

def check_metadata_pdf(doc) -> List[Finding]:
    findings = []
    try:
        import pdfplumber
        with pdfplumber.open(doc.path) as pdf:
            meta = pdf.metadata or {}
    except Exception:
        return findings

    interesting = ["Author", "Creator", "Producer", "Title", "Subject", "Keywords",
                   "LastModifiedBy", "Company"]
    for key in interesting:
        val = meta.get(key) or meta.get("/" + key)
        if val:
            sev = SEVERITY_HIGH if key in ("Author", "LastModifiedBy", "Company") else SEVERITY_MEDIUM
            findings.append(Finding(
                checker="metadata",
                severity=sev,
                category=f"pdf-{key.lower()}",
                location_label="File properties",
                location_index=0,
                evidence=f"{key}: {val}",
                note="PDFプロパティに識別情報が残っています。--sanitize で削除可能。",
            ))
    return findings


def check_metadata(doc) -> List[Finding]:
    if doc.ext == ".pptx":
        return check_metadata_pptx(doc)
    if doc.ext == ".docx":
        return check_metadata_docx(doc)
    if doc.ext == ".pdf":
        return check_metadata_pdf(doc)
    return []


# ============================================================
# Sanitization
# ============================================================

def _clear_core_properties(obj):
    """Clear python-pptx / python-docx core properties."""
    cp = obj.core_properties
    for attr in ("author", "last_modified_by", "keywords", "comments",
                 "category", "subject", "title", "identifier"):
        try:
            setattr(cp, attr, "")
        except Exception:
            pass


def sanitize_pptx(src_path: str, dst_path: str) -> List[str]:
    """Returns a list of actions performed."""
    from pptx import Presentation
    shutil.copyfile(src_path, dst_path)
    prs = Presentation(dst_path)
    _clear_core_properties(prs)
    prs.save(dst_path)

    actions = ["core properties cleared"]

    # Use zipfile to wipe docProps/app.xml company/manager fields
    actions.extend(_sanitize_openxml_zip(dst_path, is_pptx=True))
    return actions


def sanitize_docx(src_path: str, dst_path: str) -> List[str]:
    from docx import Document as DocxDocument
    shutil.copyfile(src_path, dst_path)
    d = DocxDocument(dst_path)
    _clear_core_properties(d)
    d.save(dst_path)

    actions = ["core properties cleared"]
    actions.extend(_sanitize_openxml_zip(dst_path, is_pptx=False))
    return actions


def _sanitize_openxml_zip(path: str, is_pptx: bool) -> List[str]:
    """Rewrite the zip to:
    - clear docProps/app.xml Company/Manager/HyperlinkBase
    - remove word/comments.xml (+commentsExtended, +commentsIds, +people.xml) for docx
    - strip <w:ins>/<w:del> wrappers in document.xml (accept all changes) for docx
    """
    import io

    actions = []
    p = Path(path)
    src_bytes = p.read_bytes()
    buf_out = io.BytesIO()

    WORD_COMMENT_FILES = {
        "word/comments.xml",
        "word/commentsExtended.xml",
        "word/commentsIds.xml",
        "word/commentsExtensible.xml",
        "word/people.xml",
    }

    with zipfile.ZipFile(io.BytesIO(src_bytes)) as zin:
        with zipfile.ZipFile(buf_out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)

                if item.filename == "docProps/app.xml":
                    text = data.decode("utf-8", errors="ignore")
                    for tag in ("Company", "Manager", "HyperlinkBase"):
                        text, n = re.subn(
                            rf"<{tag}\b[^>]*>.*?</{tag}>",
                            f"<{tag}></{tag}>",
                            text, flags=re.DOTALL,
                        )
                        if n:
                            actions.append(f"app.xml {tag} cleared")
                    # zero out TotalTime, revision markers
                    for tag in ("TotalTime", "Revision"):
                        text, n = re.subn(
                            rf"<{tag}\b[^>]*>.*?</{tag}>",
                            f"<{tag}>0</{tag}>",
                            text, flags=re.DOTALL,
                        )
                        if n:
                            actions.append(f"app.xml {tag} reset")
                    data = text.encode("utf-8")

                # DOCX-specific: drop comment files
                if not is_pptx and item.filename in WORD_COMMENT_FILES:
                    actions.append(f"dropped {item.filename}")
                    continue

                # DOCX: accept tracked changes in document.xml
                if not is_pptx and item.filename == "word/document.xml":
                    text = data.decode("utf-8", errors="ignore")
                    before_ins = len(re.findall(r"<w:ins\b", text))
                    before_del = len(re.findall(r"<w:del\b", text))
                    # Remove <w:ins> wrappers (keep inner content)
                    text = re.sub(r"<w:ins\b[^>]*>", "", text)
                    text = text.replace("</w:ins>", "")
                    # Remove <w:del>...</w:del> content entirely
                    text = re.sub(r"<w:del\b[^>]*>.*?</w:del>", "", text, flags=re.DOTALL)
                    # Remove comment reference anchors
                    text = re.sub(r"<w:commentRangeStart\b[^>]*/>", "", text)
                    text = re.sub(r"<w:commentRangeEnd\b[^>]*/>", "", text)
                    text = re.sub(r"<w:commentReference\b[^>]*/>", "", text)
                    if before_ins or before_del:
                        actions.append(
                            f"tracked changes accepted (ins={before_ins}, del={before_del})"
                        )
                    data = text.encode("utf-8")

                # Relationships: drop references to comments.xml for docx
                if not is_pptx and item.filename.endswith(".rels"):
                    text = data.decode("utf-8", errors="ignore")
                    new_text, n = re.subn(
                        r'<Relationship[^/]*Target="comments[^"]*"[^/]*/>',
                        "",
                        text,
                    )
                    if n:
                        actions.append(f"dropped {n} comment relationship(s)")
                    data = new_text.encode("utf-8")

                # [Content_Types].xml: drop overrides for removed comment parts
                if not is_pptx and item.filename == "[Content_Types].xml":
                    text = data.decode("utf-8", errors="ignore")
                    new_text, n = re.subn(
                        r'<Override[^/]*PartName="/word/comments[^"]*"[^/]*/>',
                        "",
                        text,
                    )
                    if n:
                        actions.append(f"[Content_Types] pruned ({n})")
                    data = new_text.encode("utf-8")

                zout.writestr(item, data)

    p.write_bytes(buf_out.getvalue())
    return actions


def sanitize_pdf(src_path: str, dst_path: str) -> List[str]:
    """Strip /Info dictionary and /Metadata stream from PDF trailer."""
    try:
        import pypdf
    except ImportError:
        return ["pypdf not installed; PDF sanitize skipped (pip install pypdf)"]

    reader = pypdf.PdfReader(src_path)
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    # Set empty metadata
    writer.add_metadata({})
    # Remove XMP metadata if present
    try:
        if "/Metadata" in writer._root_object:
            del writer._root_object["/Metadata"]
    except Exception:
        pass
    with open(dst_path, "wb") as f:
        writer.write(f)
    return ["PDF /Info cleared, /Metadata removed"]


def sanitize(src_path: str, dst_path: str, ext: str) -> List[str]:
    if ext == ".pptx":
        return sanitize_pptx(src_path, dst_path)
    if ext == ".docx":
        return sanitize_docx(src_path, dst_path)
    if ext == ".pdf":
        return sanitize_pdf(src_path, dst_path)
    return [f"unsupported ext {ext}"]
