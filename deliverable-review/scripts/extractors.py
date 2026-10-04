"""Text extraction from .pptx / .docx / .pdf with location info.

Each extractor yields TextUnit records. A TextUnit is a logical block of text
associated with a location (slide index, paragraph index, or page number) so
later phases can report where findings came from and, for pptx/docx, write
marks back to the originating shape/paragraph.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass
class TextUnit:
    kind: str                      # "text" | "table-cell" | "hyperlink" (text = link target URL)
    text: str
    location_label: str            # human-readable, e.g. "Slide 3", "Page 2", "Para 12"
    location_index: int            # slide idx (pptx), page idx (pdf), para idx (docx)
    has_image_on_page: bool = False  # true if the slide/page contains an image
    has_table_on_page: bool = False  # true if the slide/page contains a table
    # Handles back to the source object so markers.py can annotate it later.
    source_handle: Optional[Any] = None


@dataclass
class Document:
    path: str
    ext: str                         # ".pptx" | ".docx" | ".pdf"
    units: List[TextUnit] = field(default_factory=list)
    # Per-location aggregated text (used for copyright long-text + citation check)
    location_text: dict = field(default_factory=dict)
    # Per-location flags: has_image, has_table
    location_flags: dict = field(default_factory=dict)
    # Raw handle to the underlying library object (python-pptx Presentation etc.)
    raw: Any = None
    # Format-specific extras (docx: "table_loc" = {table_no: location_index})
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------
# PPTX
# ------------------------------------------------------------

def iter_shapes_recursive(shapes):
    """Yield every shape under `shapes`, descending into GroupShape recursively.

    python-pptx の `slide.shapes` / GroupShape.shapes はトップレベルしか返さない
    ため、グループ化された装飾内のテキスト・表・チャート・画像が全チェッカー
    から不可視になる。この関数を経由することで、任意ネストのグループを展開
    して個々の leaf shape を訪問できる。
    """
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    for shape in shapes:
        try:
            stype = shape.shape_type
        except Exception:
            stype = None
        if stype == MSO_SHAPE_TYPE.GROUP:
            try:
                yield from iter_shapes_recursive(shape.shapes)
            except Exception:
                pass
        else:
            yield shape


def _pptx_hyperlinks(shape) -> List[str]:
    """Link targets hidden behind display text (run hyperlinks, shape click
    actions, table-cell runs). `run.text` alone never shows them."""
    urls = []
    try:
        addr = shape.click_action.hyperlink.address
        if addr:
            urls.append(addr)
    except Exception:
        pass
    frames = []
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        frames.append(shape.text_frame)
    if getattr(shape, "has_table", False) and shape.has_table:
        frames.extend(cell.text_frame for row in shape.table.rows for cell in row.cells)
    for tf in frames:
        for para in tf.paragraphs:
            for run in para.runs:
                try:
                    addr = run.hyperlink.address
                except Exception:
                    addr = None
                if addr:
                    urls.append(addr)
    return urls


def extract_pptx(path: str) -> Document:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(path)
    doc = Document(path=path, ext=".pptx", raw=prs)

    for slide_idx, slide in enumerate(prs.slides, start=1):
        has_image = False
        has_table = False
        texts_on_slide = []

        for shape in iter_shapes_recursive(slide.shapes):
            try:
                stype = shape.shape_type
            except Exception:
                stype = None

            if stype == MSO_SHAPE_TYPE.PICTURE:
                has_image = True
            if shape.has_table:
                has_table = True
                for row in shape.table.rows:
                    for cell in row.cells:
                        t = cell.text or ""
                        if t.strip():
                            texts_on_slide.append(t)
                            doc.units.append(TextUnit(
                                kind="table-cell",
                                text=t,
                                location_label=f"Slide {slide_idx}",
                                location_index=slide_idx,
                                source_handle=cell,
                            ))
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = "".join(run.text for run in para.runs) or ""
                    if t.strip():
                        texts_on_slide.append(t)
                        doc.units.append(TextUnit(
                            kind="text",
                            text=t,
                            location_label=f"Slide {slide_idx}",
                            location_index=slide_idx,
                            source_handle=shape,
                        ))
            for url in _pptx_hyperlinks(shape):
                doc.units.append(TextUnit(
                    kind="hyperlink",
                    text=url,
                    location_label=f"Slide {slide_idx}",
                    location_index=slide_idx,
                    source_handle=shape,
                ))

        doc.location_flags[slide_idx] = {
            "has_image": has_image,
            "has_table": has_table,
            "label": f"Slide {slide_idx}",
        }
        doc.location_text[slide_idx] = "\n".join(texts_on_slide)

    # Propagate has_image/has_table flags to each unit
    for u in doc.units:
        flags = doc.location_flags.get(u.location_index, {})
        u.has_image_on_page = flags.get("has_image", False)
        u.has_table_on_page = flags.get("has_table", False)

    return doc


# ------------------------------------------------------------
# DOCX
# ------------------------------------------------------------

DOCX_BLOCK_PARAGRAPHS = 10  # 見出しが無い文書の区切り（段落数、ページ相当）


def _is_heading(para) -> bool:
    try:
        name = (para.style.name or "") if para.style is not None else ""
    except Exception:
        name = ""
    return name.startswith(("Heading", "見出し", "Title", "表題"))


def _docx_para_links(para) -> List[str]:
    try:
        return [h.url for h in para.hyperlinks if h.url]
    except Exception:
        return []


def extract_docx(path: str) -> Document:
    """Locations are heading-delimited sections (or blocks of
    DOCX_BLOCK_PARAGRAPHS paragraphs when the document has no headings), so
    that per-location checks (citation, unit mixing, 敬体/常体) don't treat a
    whole report as one page."""
    from docx import Document as DocxDocument
    from docx.table import Table

    d = DocxDocument(path)
    doc = Document(path=path, ext=".docx", raw=d)

    blocks = list(d.iter_inner_content())  # Paragraph / Table in body order
    use_headings = any(
        not isinstance(b, Table) and _is_heading(b) and (b.text or "").strip() for b in blocks
    )

    loc_idx = 0
    texts: dict = {}
    labels: dict = {}
    has_table: dict = {}
    has_image: dict = {}
    paras_in_loc = 0

    def new_loc(label: str):
        nonlocal loc_idx, paras_in_loc
        loc_idx += 1
        paras_in_loc = 0
        texts[loc_idx] = []
        labels[loc_idx] = label
        has_table[loc_idx] = False
        has_image[loc_idx] = False

    def add_links(urls, label):
        for url in urls:
            doc.units.append(TextUnit(kind="hyperlink", text=url,
                                      location_label=label, location_index=loc_idx))

    p_idx = 0
    t_idx = 0
    for b in blocks:
        if isinstance(b, Table):
            if loc_idx == 0:
                new_loc("Sec 1" if use_headings else "Block 1")
            t_idx += 1
            has_table[loc_idx] = True
            doc.extra.setdefault("table_loc", {})[t_idx] = loc_idx
            for r_idx, row in enumerate(b.rows, start=1):
                for c_idx, cell in enumerate(row.cells, start=1):
                    label = f"Table {t_idx} R{r_idx}C{c_idx}"
                    t = cell.text or ""
                    if t.strip():
                        texts[loc_idx].append(t)
                        doc.units.append(TextUnit(
                            kind="table-cell", text=t, location_label=label,
                            location_index=loc_idx, source_handle=cell,
                        ))
                    for para in cell.paragraphs:
                        add_links(_docx_para_links(para), label)
            continue

        p_idx += 1
        t = b.text or ""
        if not t.strip():
            continue
        if use_headings:
            if loc_idx == 0 or _is_heading(b):
                new_loc(f"Sec {loc_idx + 1}: {t.strip()[:20]}" if _is_heading(b) else "Sec 1")
        elif loc_idx == 0 or paras_in_loc >= DOCX_BLOCK_PARAGRAPHS:
            new_loc(f"Block {loc_idx + 1} (Para {p_idx}〜)")
        paras_in_loc += 1
        texts[loc_idx].append(t)
        if b._p.xpath(".//w:drawing | .//w:pict"):
            has_image[loc_idx] = True
        label = f"Para {p_idx}"
        doc.units.append(TextUnit(
            kind="text", text=t, location_label=label,
            location_index=loc_idx, source_handle=b,
        ))
        add_links(_docx_para_links(b), label)

    if loc_idx == 0:
        new_loc("Document")

    for i in texts:
        doc.location_flags[i] = {
            "has_image": has_image[i],
            "has_table": has_table[i],
            "label": labels[i],
        }
        doc.location_text[i] = "\n".join(texts[i])

    for u in doc.units:
        flags = doc.location_flags.get(u.location_index, {})
        u.has_image_on_page = flags.get("has_image", False)
        u.has_table_on_page = flags.get("has_table", False)

    return doc


# ------------------------------------------------------------
# PDF
# ------------------------------------------------------------

def extract_pdf(path: str) -> Document:
    import pdfplumber

    doc = Document(path=path, ext=".pdf")

    with pdfplumber.open(path) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            has_image = len(page.images) > 0
            has_table = False
            try:
                tables = page.extract_tables()
                has_table = bool(tables)
            except Exception:
                pass

            doc.location_flags[page_idx] = {
                "has_image": has_image,
                "has_table": has_table,
                "label": f"Page {page_idx}",
            }
            doc.location_text[page_idx] = text

            if text.strip():
                # Split PDF page text by paragraph (blank line) for finer reporting
                paragraphs = [p for p in text.split("\n\n") if p.strip()]
                if not paragraphs:
                    paragraphs = [text]
                for para in paragraphs:
                    doc.units.append(TextUnit(
                        kind="text",
                        text=para,
                        location_label=f"Page {page_idx}",
                        location_index=page_idx,
                        has_image_on_page=has_image,
                        has_table_on_page=has_table,
                    ))

            # Link annotations (URL behind display text)
            try:
                links = page.hyperlinks or []
            except Exception:
                links = []
            for link in links:
                uri = link.get("uri")
                if uri:
                    doc.units.append(TextUnit(
                        kind="hyperlink",
                        text=uri,
                        location_label=f"Page {page_idx}",
                        location_index=page_idx,
                        has_image_on_page=has_image,
                        has_table_on_page=has_table,
                    ))

    return doc


def extract(path: str) -> Document:
    lower = path.lower()
    if lower.endswith(".pptx"):
        return extract_pptx(path)
    if lower.endswith(".docx"):
        return extract_docx(path)
    if lower.endswith(".pdf"):
        return extract_pdf(path)
    raise ValueError(f"Unsupported file type: {path}")
