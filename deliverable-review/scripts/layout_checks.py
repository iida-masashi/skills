"""Phase 2 layout checks: title/page-number integrity, font uniformity,
tiny-font detection.
"""
import re
from collections import Counter, defaultdict
from typing import List

from checkers import Finding, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO
from extractors import iter_shapes_recursive


# ============================================================
# 1. Title / page-number integrity
# ============================================================

# Section-break layouts typically contain only a large title, often no
# main title placeholder. We allow those.
_SECTION_LAYOUT_NAMES = ("Section", "セクション", "表紙", "Title", "Cover")


def _is_cover_slide(slide_idx: int) -> bool:
    return slide_idx == 1


def _has_title_placeholder(slide) -> bool:
    try:
        t = slide.shapes.title
        if t is None:
            return False
        return bool((t.text or "").strip())
    except Exception:
        return False


def _extract_page_number_text(slide) -> List[str]:
    """Look for shapes at the bottom of the slide that contain a digit-only
    or digit/total style string. Returns text candidates."""
    candidates = []
    try:
        slide_h = slide.part.package.presentation_part.presentation.slide_height
    except Exception:
        slide_h = None
    for shape in iter_shapes_recursive(slide.shapes):
        if not shape.has_text_frame:
            continue
        txt = (shape.text_frame.text or "").strip()
        if not txt or len(txt) > 20:
            continue
        # Bottom 20% heuristic
        try:
            if slide_h and shape.top and shape.top < slide_h * 0.75:
                continue
        except Exception:
            pass
        if re.search(r"^\s*(?:\d+|\d+\s*[/／]\s*\d+|p\.?\s*\d+|page\s*\d+)\s*$", txt, re.IGNORECASE):
            candidates.append(txt)
        elif re.search(r"\d+\s*[/／]\s*\d+", txt):
            candidates.append(txt)
    return candidates


def check_title_page_number_integrity(doc) -> List[Finding]:
    findings = []
    if doc.ext != ".pptx":
        return findings

    # Title presence
    for slide_idx, slide in enumerate(doc.raw.slides, start=1):
        if _is_cover_slide(slide_idx):
            continue
        # Skip section-break slides by layout name
        try:
            layout_name = slide.slide_layout.name or ""
        except Exception:
            layout_name = ""
        if any(k.lower() in layout_name.lower() for k in _SECTION_LAYOUT_NAMES):
            continue
        if not _has_title_placeholder(slide):
            findings.append(Finding(
                checker="consulting-layout",
                severity=SEVERITY_LOW,
                category="missing-title",
                location_label=f"Slide {slide_idx}",
                location_index=slide_idx,
                evidence="(no title text)",
                note="タイトルが空または設定されていません。セクション区切り以外のスライドにはタイトルを付けるのが一般的です。",
            ))

    # Page number presence + sequence
    page_numbers_found = {}
    for slide_idx, slide in enumerate(doc.raw.slides, start=1):
        nums = _extract_page_number_text(slide)
        if nums:
            page_numbers_found[slide_idx] = nums[0]

    total_slides = len(doc.raw.slides)
    # If at least some slides have page numbers but others don't, flag missing
    # ones (skip cover).
    if page_numbers_found and len(page_numbers_found) < total_slides - 1:
        missing = [i for i in range(2, total_slides + 1) if i not in page_numbers_found]
        if missing:
            findings.append(Finding(
                checker="consulting-layout",
                severity=SEVERITY_LOW,
                category="missing-page-number",
                location_label=f"Slide {missing[0]}",
                location_index=missing[0],
                evidence=f"ページ番号なし: {missing[:10]}" + ("…" if len(missing) > 10 else ""),
                note=f"ページ番号が {len(missing)}/{total_slides} スライドで欠落しています。",
            ))

    return findings


# ============================================================
# 2. Font uniformity
# ============================================================

_DEFAULT_FONT_MARKERS = {"", None, "+mj-lt", "+mn-lt", "+mj-ea", "+mn-ea", "+mj-cs", "+mn-cs"}


def _collect_fonts_in_slide(slide):
    fonts = set()
    for shape in iter_shapes_recursive(slide.shapes):
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                try:
                    name = run.font.name
                except Exception:
                    name = None
                if name and name not in _DEFAULT_FONT_MARKERS:
                    fonts.add(name)
    return fonts


def check_font_uniformity(doc) -> List[Finding]:
    findings = []
    if doc.ext != ".pptx":
        return findings

    total_fonts = set()
    for slide_idx, slide in enumerate(doc.raw.slides, start=1):
        fonts = _collect_fonts_in_slide(slide)
        total_fonts.update(fonts)
        if len(fonts) >= 3:
            findings.append(Finding(
                checker="consulting-layout",
                severity=SEVERITY_MEDIUM,
                category="too-many-fonts-slide",
                location_label=f"Slide {slide_idx}",
                location_index=slide_idx,
                evidence=f"{len(fonts)}種類: {', '.join(sorted(fonts))[:150]}",
                note="1スライド内に3種類以上のフォントが使われています。既定フォント＋1種類に抑えるのが一般的です。",
            ))
    if len(total_fonts) >= 5:
        findings.append(Finding(
            checker="consulting-layout",
            severity=SEVERITY_LOW,
            category="too-many-fonts-file",
            location_label="File",
            location_index=0,
            evidence=f"ファイル全体で{len(total_fonts)}種類: {', '.join(sorted(total_fonts))[:200]}",
            note="ファイル全体のフォント種類が多すぎます。テンプレート整備を検討してください。",
        ))
    return findings


# ============================================================
# 3. Tiny font detection
# ============================================================

def _get_font_size_pt(run) -> float:
    try:
        sz = run.font.size
        if sz is None:
            return None
        return sz.pt
    except Exception:
        return None


def check_tiny_font(doc) -> List[Finding]:
    findings = []
    if doc.ext != ".pptx":
        return findings

    # Aggregate per slide: any run under 10pt or 8pt
    for slide_idx, slide in enumerate(doc.raw.slides, start=1):
        below_8 = []
        below_10 = []
        for shape in iter_shapes_recursive(slide.shapes):
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    pt = _get_font_size_pt(run)
                    if pt is None:
                        continue
                    rtxt = (run.text or "").strip()
                    if not rtxt:
                        continue
                    if pt < 8:
                        below_8.append((pt, rtxt[:40]))
                    elif pt < 10:
                        below_10.append((pt, rtxt[:40]))
        if below_8:
            findings.append(Finding(
                checker="consulting-layout",
                severity=SEVERITY_MEDIUM,
                category="tiny-font-8pt",
                location_label=f"Slide {slide_idx}",
                location_index=slide_idx,
                evidence=f"{len(below_8)}個: e.g. {below_8[0][1]} @ {below_8[0][0]}pt",
                note="8pt未満の極小文字が含まれます。印刷・プロジェクタ表示で読めません。",
            ))
        if below_10:
            findings.append(Finding(
                checker="consulting-layout",
                severity=SEVERITY_LOW,
                category="tiny-font-10pt",
                location_label=f"Slide {slide_idx}",
                location_index=slide_idx,
                evidence=f"{len(below_10)}個: e.g. {below_10[0][1]} @ {below_10[0][0]}pt",
                note="10pt未満の小さい文字があります。可読性を確認してください。",
            ))
    return findings


# ============================================================
# Entry
# ============================================================

def run_layout_checks(doc) -> List[Finding]:
    findings = []
    findings.extend(check_title_page_number_integrity(doc))
    findings.extend(check_font_uniformity(doc))
    findings.extend(check_tiny_font(doc))
    return findings
