# PRD-02: PDF Assembly & Sherwin-Williams Branded Report Generation
**Site Audit Agent — Asset Protection Manager Reporting Tool**

---

## Document Information

| Field | Value |
|---|---|
| Document ID | PRD-02 |
| Feature Name | PDF Assembly & SW Branded Report Generation |
| Version | 1.0 |
| Date | 2026-05-05 |
| Author | PM Agent (Claude Code) |
| Status | Draft — Ready for Engineering Review |
| Depends On | PRD-01 (Intake Form & AI Content Generation) |

---

## 1. Overview

PRD-02 covers the second major pipeline stage of the Site Audit Agent: consuming structured AI-generated assessment content produced in PRD-01 and assembling it into a polished, client-ready PDF report with full Sherwin-Williams branding.

The output of this pipeline stage is a downloadable PDF that an APM can hand directly to a facility owner or maintenance manager without any further editing.

---

## 2. Problem Statement

APMs currently produce site assessment reports manually — copying AI or hand-written findings into Word documents, attaching photos individually, and applying SW branding inconsistently. This process is time-consuming, error-prone, and produces outputs of uneven quality.

**Desired State:** Once an APM completes the PRD-01 intake form and AI content is generated, a single button press produces a fully branded, professionally structured PDF report — ready for immediate client delivery.

---

## 3. Goals & Objectives

### Primary Goal
Produce a client-presentable, Sherwin-Williams branded PDF report from AI-generated content with zero manual formatting effort from the APM.

### Secondary Goals
- Consistent visual branding across all reports regardless of generating APM
- Reasonable PDF file size for email delivery
- Reusable template architecture updatable centrally
- Foundation for PRD-03 (PDS hyperlinks) without requiring template restructuring

### Non-Goals
- Hyperlink generation or PDS URL injection (PRD-03)
- AI content generation logic (PRD-01)
- Report storage/retrieval (PRD-04)
- Report versioning or email delivery
- Interactive or editable PDF features

---

## 4. Target Users

### Primary: Asset Protection Manager (APM)
Field representative conducting facility coating assessments. Goal: download a PDF and send it to the client without opening an editor.

### Secondary: Facility Owner / Maintenance Manager (Report Recipient)
Can navigate the report, find the photo log and recommendations, and understand next steps without calling the APM.

---

## 5. Proposed Solution

Two-component system:

1. **`assets/pdf_template.html`** — Jinja2-compatible HTML/CSS template defining visual structure and branding. WeasyPrint renders this to PDF server-side.

2. **`src/pdf_builder.py`** — Assembly engine. Accepts AI-generated content dict + photo files, processes photos via Pillow, injects content into template via Jinja2, invokes WeasyPrint, returns raw PDF bytes.

---

## 6. Functional Requirements

### FR-01: Cover Page
- SW logo (`assets/sw_logo.png`) upper-left
- Report title: "Site Assessment Report"
- Facility name, client/owner name, APM name, assessment date (Month DD, YYYY)
- SW color treatment using `#C01F2B`
- Exactly one full page; no body content from other sections

### FR-02: Table of Contents
Page 2 with auto-generated section listing and accurate page numbers via WeasyPrint CSS `target-counter`.

Sections: Executive Summary | Photo Log & Observed Failure Analysis | Recommended Coating System | Surface Preparation Standards | Appendix

### FR-03: Executive Summary Section
Multi-paragraph AI-generated executive summary. Section header in SW brand color. Variable-length content accommodated without overflow.

### FR-04: Photo Log & Observed Failure Analysis Section
For each photo:
- Photo image inline
- AI-generated failure analysis caption below
- Photos in submission order
- Photo-caption pairs visually grouped (bordered card)
- No photo-caption pair split across a page break

Photo processing (in `pdf_builder.py`):
- Max rendered width: 480px
- Proportional resize via Pillow (no distortion)
- JPEG quality=75 before base64 encoding
- Original files not modified

### FR-05: Recommended Coating System Section
- Coating system name (heading)
- System description (body text, multi-paragraph)
- Product Data Sheet references as bulleted list (plain text in PRD-02; hyperlinks added in PRD-03)
- Coat sequence (primer, intermediate, topcoat) if provided

### FR-06: Surface Preparation Standards Section
Structured list of AMPP and ICRI references. Each entry: standard designation, name/description, applicability note if provided.

### FR-07: Appendix Section
PDS references, technical bulletins, supplemental notes as plain text (hyperlinks deferred to PRD-03).

### FR-08: Branded Footer — Every Page
- SW wordmark or brand identifier
- "Confidential — Prepared for [Client Name]"
- "Page N of M" (total page count required)
- Consistent across all pages; does not overlap body content

### FR-09: PDF Delivery via Streamlit
`pdf_builder.py` exposes `build_pdf(content: dict, photo_paths: list[str]) -> bytes`. Returns raw PDF bytes. Does not write files to disk or interact with Streamlit session directly.

### FR-10: Error Handling
- Missing photo file: log warning, substitute placeholder or skip, continue generation
- Missing optional fields: render "Not provided" placeholder
- WeasyPrint failure: raise typed `PDFBuildError` exception

---

## 7. Technical Specifications

### 7.1 File Structure

```
Site_Audit_Agent/
├── assets/
│   ├── pdf_template.html        # Jinja2 HTML/CSS template
│   └── sw_logo.png              # Official SW logo (provided by user)
├── src/
│   └── pdf_builder.py           # PDF assembly module
```

### 7.2 Dependencies

| Package | Min Version | Purpose |
|---|---|---|
| `weasyprint` | 61.0 | HTML-to-PDF rendering |
| `jinja2` | 3.1 | Template rendering |
| `Pillow` | 10.0 | Photo resizing and compression |
| `python-dateutil` | 2.8 | Date formatting for cover page |

### 7.3 Content Dictionary Schema

```python
content = {
    # Cover page
    "facility_name": str,           # required
    "client_name": str,             # required
    "apm_name": str,                # required
    "assessment_date": str,         # required — ISO 8601 (YYYY-MM-DD)

    # Executive summary
    "executive_summary": str,       # required — may contain \n paragraph breaks

    # Photo log
    "photos": [                     # required — list may be empty
        {
            "file_path": str,       # required
            "caption": str,         # required — AI-generated failure analysis
        },
    ],

    # Coating system
    "coating_system": {
        "name": str,                # required
        "description": str,         # required
        "coat_sequence": [          # optional
            {"coat": str, "product": str},
        ],
        "pds_references": [str],    # optional — plain text in PRD-02
    },

    # Standards
    "standards": [                  # optional
        {
            "designation": str,     # required if entry present
            "name": str,            # required if entry present
            "applicability": str,   # optional
        },
    ],

    # Appendix
    "appendix_items": [str],        # optional
}
```

### 7.4 `pdf_builder.py` Public Interface

```python
def build_pdf(content: dict, photo_paths: list[str] | None = None) -> bytes:
    """
    Assemble a branded SW Site Assessment PDF from AI-generated content.
    Returns raw PDF bytes suitable for st.download_button() or file write.
    Raises PDFBuildError if WeasyPrint rendering fails.
    """

class PDFBuildError(Exception):
    """Raised when WeasyPrint fails to render the PDF."""
    pass
```

### 7.5 Template Architecture

`pdf_template.html` must use:
- CSS `@page` rule for margins, page size (US Letter: 8.5in x 11in), and footer
- CSS `counter(page)` and `counter(pages)` for accurate page numbering
- Jinja2 block tags for each report section
- Inline base64-encoded images (no external HTTP requests at render time)
- CSS print media conventions compatible with WeasyPrint's Pango/Cairo renderer

### 7.6 SW Brand Specifications

Sourced from official Sherwin-Williams Employer Brand Guidelines (March 2025).

| Element | Value | Source |
|---|---|---|
| SW Red (primary accent) | `#F5333F` (PMS 032, RGB 245/51/63) | Official style guide |
| SW Blue (primary brand) | `#003DA5` (PMS 293, RGB 0/61/165) | Official style guide |
| Neutral dark (body text) | `#2C2C2C` | Standard |
| Light background / rules | `#F2F2F2` | Standard |
| Body font | Arial (all weights) | Official style guide |
| Cover page title size | 28pt | — |
| Section heading size | 16pt | — |
| Body text size | 10pt | — |
| Footer text size | 8pt | — |

**Report layout informed by example audit (White Drive Site Assessment, Dan Jochum):**
- Running header each page: `{Facility} | Site Assessment | Attention: {Client}`
- Running footer: `Prepared by {APM Name} | Page X`
- Photo log: two-column grid layout (photo left, caption right)
- Coating system: three-column table (Layer/Step | Product & Critical Info | Reason for Recommendation)
- Conditions table: two-column (Observed Condition | Assessment Note)

### 7.7 Photo Processing Pipeline

```
1. Open file with Pillow Image.open()
2. Convert to RGB (handles RGBA/palette PNGs)
3. Scale: max_width=960px (2x for print density), preserve aspect ratio
4. Resize with Image.LANCZOS resampling
5. Save to in-memory BytesIO buffer as JPEG, quality=75
6. Base64-encode buffer contents
7. Embed as data URI: "data:image/jpeg;base64,{encoded}"
```

### 7.8 Performance Requirements

| Metric | Target |
|---|---|
| PDF generation time (10 photos) | Under 15 seconds on Hostinger VPS |
| Output PDF file size (10 photos) | Under 8 MB |
| Output PDF file size (0 photos) | Under 500 KB |

---

## 8. User Stories

**US-201 — Generate branded PDF from AI content**
APM clicks one button → PDF downloads within 15 seconds with filename `SW_SiteAudit_{facility_name}_{YYYY-MM-DD}.pdf`.

**US-202 — Cover page displays all required fields**
Cover page contains facility name, client name, APM name, formatted date, SW logo, and `#C01F2B` brand treatment. No body content on page 1.

**US-203 — Table of contents with accurate page numbers**
Page 2 lists all five sections with correct dynamically generated page numbers.

**US-204 — Footer on every page**
Every page shows "Page N of M", "Confidential — Prepared for [Client Name]", and SW brand identifier without overlapping body content.

**US-205 — Photos with AI captions**
Each photo appears in submission order paired with its AI caption in a bordered card. No pair splits across page break.

**US-206 — Photos resized for reasonable file size**
10 smartphone-resolution photos produce a PDF under 8 MB. No distortion. Original files unchanged.

**US-207 — Missing photo handled gracefully**
PDF generates successfully with a placeholder for the missing photo. No unhandled exception raised.

**US-208 — Coating system section renders coat sequence**
System name, description, coat sequence, and PDS references (plain text) all render correctly.

**US-209 — AMPP/ICRI standards as structured list**
Each standard renders with designation, name, and optional applicability note.

**US-210 — Optional fields display placeholder when absent**
Absent optional fields render "Not provided for this assessment." — no Python errors.

**US-211 — SW brand colors applied consistently**
Section headers use `#C01F2B`, body text uses `#2C2C2C`, no off-brand colors on any page.

---

## 9. Acceptance Criteria Summary

| Gate | Criterion | Verification |
|---|---|---|
| AC-01 | `build_pdf()` returns valid PDF bytes for full content dict | Automated test |
| AC-02 | All 7 sections in correct order | Manual QA |
| AC-03 | Cover page has all required fields and SW branding | Manual QA |
| AC-04 | TOC page numbers match actual section positions | Manual QA |
| AC-05 | Footer on all pages with correct N/M count | Manual QA |
| AC-06 | 10-photo PDF generated in under 15s on VPS | Timed integration test |
| AC-07 | 10-photo PDF under 8 MB | File size assertion |
| AC-08 | Missing photo does not raise unhandled exception | Automated test |
| AC-09 | Minimal content dict (required fields only) generates cleanly | Automated test |
| AC-10 | WeasyPrint failure raises `PDFBuildError` | Automated test with mock |
| AC-11 | Original photo files unchanged after `build_pdf()` | File hash comparison |
| AC-12 | PDF filename follows `SW_SiteAudit_{facility_name}_{YYYY-MM-DD}.pdf` | UI inspection |

---

## 10. Out of Scope for PRD-02

| Item | Deferred To |
|---|---|
| PDS hyperlinks (plain text only in this PRD) | PRD-03 |
| Report storage or retrieval | PRD-04 |
| Report versioning | Future PRD |
| Email delivery | Future PRD |
| User authentication | Future PRD |
| Per-client custom branding | Future PRD |
| Multi-language support | Future PRD |

---

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| WeasyPrint CSS gaps (e.g., `target-counter` for TOC) | Medium | High | Prototype TOC technique early; fallback: static section listing |
| SW logo not provided before dev begins | High | Low | Placeholder slot designed in from day one; 1-file swap when ready |
| PDF generation time exceeds 15s on VPS | Medium | Medium | Benchmark on VPS in Week 1; reduce Pillow quality if needed |
| VPS missing WeasyPrint system deps | Medium | High | Validate environment and document in README before committing to stack |
| Content dict schema drift between PRD-01 and PRD-02 | Medium | High | Section 7.3 is the canonical contract; schema changes require cross-PRD notification |

---

## 12. Open Questions

1. Logo file format and dimensions — white/reverse variant for `#C01F2B` cover background?
2. Page size — US Letter assumed; confirm for all APM regions (A4?)
3. Photo order — submission order correct, or should APMs be able to sequence?
4. "Confidential" footer text — approved by SW Legal?
5. Coat sequence data — does PRD-01 AI produce structured primer/intermediate/topcoat entries?

---

*End of PRD-02 — Site Audit Agent: PDF Assembly & SW Branded Report Generation*
*Version 1.0 | 2026-05-05*
