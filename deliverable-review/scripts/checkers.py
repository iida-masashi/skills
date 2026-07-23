"""Five checkers for deliverable-review.

Each checker consumes a Document and returns a list of Finding records.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import patterns as P


SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"
SEVERITY_INFO = "INFO"


@dataclass
class Finding:
    checker: str                   # "url-contamination" | "ai-trace" | "copyright" | "url-liveness" | "verifiable-claim"
    severity: str                  # HIGH | MEDIUM | LOW | INFO
    category: str                  # sub-category within checker
    location_label: str
    location_index: int
    evidence: str                  # matched string / snippet
    note: str = ""                 # extra context
    source_handle: Optional[Any] = None


# ------------------------------------------------------------
# 1. URL contamination
# ------------------------------------------------------------

def check_url_contamination(doc) -> List[Finding]:
    findings = []
    for u in doc.units:
        for category, evidence in P.find_url_contamination(u.text):
            sev = SEVERITY_HIGH if category != "general-tracking-param" else SEVERITY_MEDIUM
            findings.append(Finding(
                checker="url-contamination",
                severity=sev,
                category=category,
                location_label=u.location_label,
                location_index=u.location_index,
                evidence=evidence,
                note="顧客提出資料にAIツール/トラッキングの痕跡URLが混入しています。",
                source_handle=u.source_handle,
            ))
    return findings


# ------------------------------------------------------------
# 2. AI generation traces
# ------------------------------------------------------------

def check_ai_traces(doc) -> List[Finding]:
    findings = []
    for u in doc.units:
        for category, evidence in P.find_ai_traces(u.text):
            sev = SEVERITY_HIGH if category in ("AI-phrase-ja", "AI-phrase-en") else SEVERITY_MEDIUM
            if category == "markdown-remnant":
                sev = SEVERITY_LOW
            findings.append(Finding(
                checker="ai-trace",
                severity=sev,
                category=category,
                location_label=u.location_label,
                location_index=u.location_index,
                evidence=evidence[:200],
                note="AI生成物の貼り付け痕跡の可能性があります。",
                source_handle=u.source_handle,
            ))
    return findings


# ------------------------------------------------------------
# 3. Copyright risk
# ------------------------------------------------------------

def check_copyright(doc) -> List[Finding]:
    """Long text without citation, plus images/tables without citation on page."""
    findings = []

    # (a) Per-location: long text without citation
    for loc_idx, text in doc.location_text.items():
        flags = doc.location_flags.get(loc_idx, {})
        label = flags.get("label", f"Loc {loc_idx}")
        if len(text) >= P.LONG_TEXT_THRESHOLD and not P.has_citation(text):
            findings.append(Finding(
                checker="copyright",
                severity=SEVERITY_MEDIUM,
                category="long-text-without-citation",
                location_label=label,
                location_index=loc_idx,
                evidence=text[:150] + ("…" if len(text) > 150 else ""),
                note=f"{P.LONG_TEXT_THRESHOLD}文字以上の本文があるが、出典記載 (出典/Source/URL等) が見当たりません。",
            ))

    # (b) Images on page without citation
    for loc_idx, flags in doc.location_flags.items():
        text = doc.location_text.get(loc_idx, "")
        label = flags.get("label", f"Loc {loc_idx}")
        if flags.get("has_image") and not P.has_citation(text):
            findings.append(Finding(
                checker="copyright",
                severity=SEVERITY_MEDIUM,
                category="image-without-citation",
                location_label=label,
                location_index=loc_idx,
                evidence="(image present)",
                note="画像があるが、出典記載が見当たりません。自作・フリー素材でない場合は出典明記を検討してください。",
            ))
        if flags.get("has_table") and not P.has_citation(text):
            findings.append(Finding(
                checker="copyright",
                severity=SEVERITY_LOW,
                category="table-without-citation",
                location_label=label,
                location_index=loc_idx,
                evidence="(table present)",
                note="表があるが、出典記載が見当たりません。データ引用の場合は出典明記を検討してください。",
            ))

    return findings


# ------------------------------------------------------------
# 4. URL liveness (HEAD request)
# ------------------------------------------------------------

def check_url_liveness(doc, timeout: float = 5.0, max_workers: int = 10) -> List[Finding]:
    import requests

    # Collect unique URLs with their locations
    url_to_locations = {}  # url -> list of (label, idx, handle)
    for u in doc.units:
        for url in P.extract_all_urls(u.text):
            url_to_locations.setdefault(url, []).append(
                (u.location_label, u.location_index, u.source_handle)
            )

    def probe(url: str):
        try:
            headers = {"User-Agent": "Mozilla/5.0 deliverable-review"}
            r = requests.head(url, timeout=timeout, allow_redirects=True, headers=headers)
            # Some servers reject HEAD; retry GET
            if r.status_code >= 400:
                r = requests.get(url, timeout=timeout, allow_redirects=True, headers=headers, stream=True)
                r.close()
            return url, r.status_code, None
        except requests.RequestException as e:
            return url, None, str(e.__class__.__name__)

    findings = []
    if not url_to_locations:
        return findings

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(probe, url) for url in url_to_locations]
        for fut in as_completed(futures):
            url, status, err = fut.result()
            if err is not None:
                for label, idx, handle in url_to_locations[url]:
                    findings.append(Finding(
                        checker="url-liveness",
                        severity=SEVERITY_HIGH,
                        category="unreachable",
                        location_label=label,
                        location_index=idx,
                        evidence=url,
                        note=f"URLに到達できません ({err})。ハルシネーションの可能性。",
                        source_handle=handle,
                    ))
            elif status is not None and status >= 400:
                sev = SEVERITY_HIGH if status in (404, 410) else SEVERITY_MEDIUM
                for label, idx, handle in url_to_locations[url]:
                    findings.append(Finding(
                        checker="url-liveness",
                        severity=sev,
                        category=f"http-{status}",
                        location_label=label,
                        location_index=idx,
                        evidence=url,
                        note=f"HTTP {status}。URLが存在しないか、アクセス不可。",
                        source_handle=handle,
                    ))
    return findings


# ------------------------------------------------------------
# 5. Verifiable claims (numbers/dates/rankings WITHOUT citation nearby)
# ------------------------------------------------------------

def check_verifiable_claims(doc) -> List[Finding]:
    findings = []
    for u in doc.units:
        # Skip units whose location has a citation — those claims are nominally sourced
        loc_text = doc.location_text.get(u.location_index, "")
        if P.has_citation(loc_text):
            continue
        claims = P.extract_verifiable_claims(u.text)
        for category, evidence in claims:
            findings.append(Finding(
                checker="verifiable-claim",
                severity=SEVERITY_INFO,
                category=category,
                location_label=u.location_label,
                location_index=u.location_index,
                evidence=evidence,
                note="出典記載がない箇所の検証要主張です。裏取りしてください。",
                source_handle=u.source_handle,
            ))
    return findings


# ------------------------------------------------------------
# Orchestration
# ------------------------------------------------------------

def run_all(doc, skip_liveness: bool = False) -> List[Finding]:
    import numeric_integrity
    import metadata as metadata_mod
    import internal_content
    import style_checks
    import layout_checks

    findings = []
    findings.extend(check_url_contamination(doc))
    findings.extend(check_ai_traces(doc))
    findings.extend(check_copyright(doc))
    if not skip_liveness:
        findings.extend(check_url_liveness(doc))
    findings.extend(check_verifiable_claims(doc))
    findings.extend(numeric_integrity.run_numeric_integrity(doc))
    findings.extend(metadata_mod.check_metadata(doc))
    findings.extend(internal_content.run_internal_content(doc))
    findings.extend(style_checks.run_style_checks(doc))
    findings.extend(layout_checks.run_layout_checks(doc))
    return findings
