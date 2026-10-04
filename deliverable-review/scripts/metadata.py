"""Metadata inspection and sanitization for .pptx / .docx / .pdf.

Detection: always enumerate what's present (author, company, custom props,
revisions, comments, etc.).
Sanitization (--sanitize flag): writes a <stem>_sanitized.<ext> with sensitive
metadata removed:
  - core properties, docProps/app.xml Company/Manager/HyperlinkBase
  - docProps/custom.xml properties (MSIP_Label_* 秘密度ラベルは保持)
  - docx: comments parts, tracked changes accepted (body/header/footer/notes)
  - pptx: comments (legacy + modern) and comment authors
  - pdf: /Info and XMP /Metadata
Hidden slides and speaker notes are *reported only* (not deleted) since they
may be intentional.

OOXML is edited with lxml (never regex) and the result is re-opened and
re-checked by `verify_sanitized`.
"""
import io
import posixpath
import re
import shutil
import zipfile
from pathlib import Path
from typing import List, Optional, Set

from lxml import etree

from checkers import Finding, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO


_CORE_ATTRS = [
    ("author", "作成者"),
    ("last_modified_by", "最終更新者"),
    ("keywords", "キーワード"),
    ("comments", "コメント(プロパティ)"),
    ("category", "カテゴリ"),
    ("subject", "題目"),
    ("title", "タイトル"),
]

_APP_TAGS = ("Company", "Manager", "HyperlinkBase")

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = "{%s}" % _W_NS
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_CUSTOM_NS = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"

_WORD_STORY_RE = re.compile(r"^word/(?:document|header\d*|footer\d*|footnotes|endnotes)\.xml$")
_WORD_COMMENT_PART_RE = re.compile(r"^word/(?:comments\w*|people)\.xml$")
_PPT_COMMENT_PART_RE = re.compile(r"^ppt/(?:comments/.+|commentAuthors\.xml|authors\.xml)$")
_TRACKED_CHANGE_RE = re.compile(r"<w:(?:ins|del|moveFrom|moveTo|rPrChange|pPrChange)\b")
_MSIP_PREFIX = "MSIP_Label_"


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


# ------------------------------------------------------------
# Detection helpers
# ------------------------------------------------------------

def _core_property_findings(cp) -> List[Finding]:
    findings = []
    for attr, label in _CORE_ATTRS:
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
    return findings


def _custom_property_names(xml_bytes: bytes) -> List[str]:
    root = etree.fromstring(xml_bytes)
    return [p.get("name", "") for p in root if _local(p.tag) == "property"]


def _package_property_findings(path: str) -> List[Finding]:
    """docProps/app.xml (Company/Manager/HyperlinkBase) and docProps/custom.xml."""
    findings = []
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "docProps/app.xml" in names:
                root = etree.fromstring(z.read("docProps/app.xml"))
                for el in root:
                    tag = _local(el.tag)
                    if tag in _APP_TAGS and (el.text or "").strip():
                        findings.append(Finding(
                            checker="metadata",
                            severity=SEVERITY_HIGH if tag == "Company" else SEVERITY_MEDIUM,
                            category=f"app-{tag.lower()}",
                            location_label="File properties",
                            location_index=0,
                            evidence=f"{tag}: {el.text.strip()}",
                            note="アプリケーションプロパティに識別情報が残っています。--sanitize で削除可能。",
                        ))
            if "docProps/custom.xml" in names:
                custom = [n for n in _custom_property_names(z.read("docProps/custom.xml"))
                          if not n.startswith(_MSIP_PREFIX)]
                if custom:
                    findings.append(Finding(
                        checker="metadata",
                        severity=SEVERITY_MEDIUM,
                        category="custom-properties",
                        location_label="File properties",
                        location_index=0,
                        evidence=", ".join(custom)[:200],
                        note="ユーザー設定プロパティが残っています（社内管理番号等の可能性）。"
                             "--sanitize で削除可能（秘密度ラベル MSIP_Label_* は保持）。",
                    ))
    except Exception:
        pass
    return findings


# ------------------------------------------------------------
# Format-specific detection
# ------------------------------------------------------------

def check_metadata_pptx(doc) -> List[Finding]:
    # Hidden slides are reported by internal_content (avoid duplicate HIGH).
    findings = _core_property_findings(doc.raw.core_properties)
    findings.extend(_package_property_findings(doc.path))
    return findings


def check_metadata_docx(doc) -> List[Finding]:
    findings = _core_property_findings(doc.raw.core_properties)
    findings.extend(_package_property_findings(doc.path))

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
            tracked_parts = [
                n for n in names
                if _WORD_STORY_RE.match(n)
                and _TRACKED_CHANGE_RE.search(z.read(n).decode("utf-8", errors="ignore"))
            ]
            if tracked_parts:
                findings.append(Finding(
                    checker="metadata",
                    severity=SEVERITY_HIGH,
                    category="docx-tracked-changes",
                    location_label="File",
                    location_index=0,
                    evidence="tracked changes present: " + ", ".join(tracked_parts),
                    note="変更履歴(Track Changes)が残っています。--sanitize で受け入れ削除します。",
                ))
    except Exception:
        pass

    return findings


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


def _to_xml_bytes(root) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _unwrap(el) -> None:
    parent = el.getparent()
    idx = parent.index(el)
    for child in list(el):
        parent.insert(idx, child)
        idx += 1
    parent.remove(el)


def _accept_tracked_changes(xml_bytes: bytes):
    """Accept all revisions in a WordprocessingML story part.

    - <w:ins>/<w:moveTo> wrappers: unwrap (keep content)
    - <w:del>/<w:moveFrom> wrappers: drop with content
    - revision markers inside property elements (<w:rPr><w:del/></w:rPr> 等):
      drop the marker only; a deleted table row (<w:trPr><w:del/>) drops the row
    - *PrChange (formatting history) and move range markers: drop
    - comment anchors: drop (comment parts are removed separately)
    Returns (new_bytes, ins_count, del_count).
    """
    root = etree.fromstring(xml_bytes)
    n_ins = n_del = 0

    for el in list(root.iter(_W + "del", _W + "moveFrom")):
        parent = el.getparent()
        if parent is None:
            continue
        n_del += 1
        ptag = _local(parent.tag)
        if ptag == "trPr":
            row = parent.getparent()
            if row is not None and row.getparent() is not None:
                row.getparent().remove(row)
        else:
            parent.remove(el)  # marker in rPr, or wrapper with deleted content

    for el in list(root.iter(_W + "ins", _W + "moveTo")):
        parent = el.getparent()
        if parent is None:
            continue
        n_ins += 1
        if _local(parent.tag).endswith("Pr"):
            parent.remove(el)
        else:
            _unwrap(el)

    drop_tags = [_W + t for t in (
        "rPrChange", "pPrChange", "sectPrChange", "tblPrChange", "tblGridChange",
        "trPrChange", "tcPrChange", "tblPrExChange", "numberingChange",
        "moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd",
        "commentRangeStart", "commentRangeEnd",
    )]
    for el in list(root.iter(*drop_tags)):
        if el.getparent() is not None:
            el.getparent().remove(el)

    for ref in list(root.iter(_W + "commentReference")):
        run = ref.getparent()
        run.remove(ref)
        # Drop the now-empty run (only rPr left)
        if run.getparent() is not None and all(_local(c.tag) == "rPr" for c in run):
            run.getparent().remove(run)

    return _to_xml_bytes(root), n_ins, n_del


def _strip_custom_properties(xml_bytes: bytes):
    root = etree.fromstring(xml_bytes)
    removed = 0
    for p in list(root):
        if _local(p.tag) == "property" and not p.get("name", "").startswith(_MSIP_PREFIX):
            root.remove(p)
            removed += 1
    # pid は連番である必要はないが、2 以上で一意であればよい（保持分はそのまま）
    return _to_xml_bytes(root), removed


def _rels_source_dir(rels_name: str) -> str:
    # "word/_rels/document.xml.rels" -> "word" ; "_rels/.rels" -> ""
    return posixpath.dirname(posixpath.dirname(rels_name))


def _drop_relationships(xml_bytes: bytes, rels_name: str, removed: Set[str]):
    root = etree.fromstring(xml_bytes)
    base = _rels_source_dir(rels_name)
    n = 0
    for rel in list(root):
        if rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target", "")
        part = target[1:] if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))
        if part in removed:
            root.remove(rel)
            n += 1
    return _to_xml_bytes(root), n


def _drop_content_type_overrides(xml_bytes: bytes, removed: Set[str]):
    root = etree.fromstring(xml_bytes)
    n = 0
    for el in list(root):
        if _local(el.tag) == "Override" and el.get("PartName", "").lstrip("/") in removed:
            root.remove(el)
            n += 1
    return _to_xml_bytes(root), n


def _sanitize_openxml_zip(path: str, is_pptx: bool) -> List[str]:
    """Rewrite the package:
    - clear docProps/app.xml Company/Manager/HyperlinkBase, reset TotalTime/Revision
    - strip docProps/custom.xml properties except MSIP_Label_* (sensitivity label)
    - docx: drop comment parts, accept tracked changes in all story parts
    - pptx: drop comment parts (legacy + modern) and comment authors
    - drop relationships / content-type overrides pointing to removed parts
    """
    actions = []
    p = Path(path)
    src_bytes = p.read_bytes()

    with zipfile.ZipFile(io.BytesIO(src_bytes)) as zin:
        infos = zin.infolist()
        comment_re = _PPT_COMMENT_PART_RE if is_pptx else _WORD_COMMENT_PART_RE
        removed = {i.filename for i in infos
                   if comment_re.match(i.filename) and not i.filename.endswith(".rels")}
        # rels of removed parts go too (e.g. ppt/comments/_rels/...)
        removed_rels = {i.filename for i in infos
                        if comment_re.match(i.filename) and i.filename.endswith(".rels")}

        buf_out = io.BytesIO()
        with zipfile.ZipFile(buf_out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in infos:
                name = item.filename
                if name in removed or name in removed_rels:
                    actions.append(f"dropped {name}")
                    continue
                data = zin.read(name)

                if name == "docProps/app.xml":
                    root = etree.fromstring(data)
                    for el in root:
                        tag = _local(el.tag)
                        if tag in _APP_TAGS and (el.text or "").strip():
                            el.text = ""
                            actions.append(f"app.xml {tag} cleared")
                        elif tag in ("TotalTime", "Revision") and (el.text or "0") != "0":
                            el.text = "0"
                            actions.append(f"app.xml {tag} reset")
                    data = _to_xml_bytes(root)

                elif name == "docProps/custom.xml":
                    data, n = _strip_custom_properties(data)
                    if n:
                        actions.append(f"custom.xml {n} propert(y/ies) removed (MSIP labels kept)")

                elif not is_pptx and _WORD_STORY_RE.match(name):
                    data, n_ins, n_del = _accept_tracked_changes(data)
                    if n_ins or n_del:
                        actions.append(f"{name}: tracked changes accepted (ins={n_ins}, del={n_del})")

                elif name.endswith(".rels") and removed:
                    data, n = _drop_relationships(data, name, removed)
                    if n:
                        actions.append(f"{name}: dropped {n} relationship(s)")

                elif name == "[Content_Types].xml" and removed:
                    data, n = _drop_content_type_overrides(data, removed)
                    if n:
                        actions.append(f"[Content_Types] pruned ({n})")

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
    # Drop /Info entirely (pypdf would otherwise stamp /Producer)
    writer.metadata = None
    try:
        if "/Metadata" in writer._root_object:
            del writer._root_object["/Metadata"]
    except Exception:
        pass
    with open(dst_path, "wb") as f:
        writer.write(f)
    return ["PDF /Info removed, /Metadata removed"]


# Categories that --sanitize is supposed to eliminate
_SANITIZABLE_PREFIXES = ("core-", "app-", "custom-properties", "docx-comments",
                         "docx-tracked-changes", "docx-comment", "pptx-comment", "pdf-")


def verify_sanitized(path: str) -> List[str]:
    """Re-open the sanitized file and re-run detection.

    Raises RuntimeError if the file cannot be opened (corrupted package).
    Returns human-readable residual findings (empty list = clean).
    """
    import extractors
    import internal_content
    try:
        doc = extractors.extract(path)
    except Exception as e:
        raise RuntimeError(f"サニタイズ結果を開けません（ファイル破損の可能性）: {type(e).__name__}: {e}")
    residual = check_metadata(doc) + internal_content.run_internal_content(doc)
    return [f"{f.category}: {f.evidence}" for f in residual
            if f.category.startswith(_SANITIZABLE_PREFIXES)]


def sanitize(src_path: str, dst_path: str, ext: str) -> List[str]:
    if ext == ".pptx":
        actions = sanitize_pptx(src_path, dst_path)
    elif ext == ".docx":
        actions = sanitize_docx(src_path, dst_path)
    elif ext == ".pdf":
        actions = sanitize_pdf(src_path, dst_path)
    else:
        return [f"unsupported ext {ext}"]
    residual = verify_sanitized(dst_path)
    if residual:
        actions.append("verify: 残存あり → " + " / ".join(residual))
    else:
        actions.append("verify: OK（再オープン・再検出で残存なし）")
    return actions
