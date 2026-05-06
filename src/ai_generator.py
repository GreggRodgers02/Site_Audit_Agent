"""
ai_generator.py
---------------
OpenAI API integration for the Site Audit Agent.

1. Optionally researches the coating system online via OpenAI Responses API web search.
2. Sends each uploaded photo through the vision API for per-photo failure analysis.
3. Generates a consolidated professional site assessment narrative (8 sections).

Returns a content dict for direct consumption by pdf_builder.build_pdf().
"""

from __future__ import annotations

import base64
import os
import logging
from datetime import date
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class AIGenerationError(Exception):
    """Raised on any unrecoverable failure during AI-powered report generation."""


def _get_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AIGenerationError(
            "The 'openai' package is not installed. Run: pip install openai>=1.30.0"
        ) from exc

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise AIGenerationError(
            "OPENAI_API_KEY is not set. Add it to your .env file and restart."
        )
    return OpenAI(api_key=api_key)


def _primary_model() -> str:
    return os.environ.get("OPENAI_PRIMARY_MODEL", "gpt-4o").strip()


def _fallback_model() -> str:
    return os.environ.get("OPENAI_FALLBACK_MODEL", "gpt-4o-mini").strip()


def _encode_image(uploaded_file) -> str:
    uploaded_file.seek(0)
    return base64.b64encode(uploaded_file.read()).decode("utf-8")


def _image_media_type(uploaded_file) -> str:
    name = getattr(uploaded_file, "name", "").lower()
    return "image/png" if name.endswith(".png") else "image/jpeg"


def _chat_completion(
    client, model: str, messages: list[dict], max_tokens: int = 4096
) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_completion_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def _call_with_fallback(
    client, messages: list[dict], max_tokens: int = 4096
) -> str:
    primary = _primary_model()
    fallback = _fallback_model()
    try:
        return _chat_completion(client, primary, messages, max_tokens=max_tokens)
    except Exception as primary_exc:
        error_str = str(primary_exc).lower()
        fallback_triggers = (
            "model", "not found", "does not exist", "invalid model",
            "unavailable", "overloaded", "capacity",
        )
        if not any(t in error_str for t in fallback_triggers):
            _translate_api_error(primary_exc)
        logger.warning(
            "Primary model '%s' unavailable (%s). Falling back to '%s'.",
            primary, primary_exc, fallback,
        )
        try:
            return _chat_completion(client, fallback, messages, max_tokens=max_tokens)
        except Exception as fallback_exc:
            _translate_api_error(fallback_exc)


def _translate_api_error(exc: Exception) -> None:
    error_str = str(exc).lower()
    if "rate limit" in error_str or "429" in error_str:
        raise AIGenerationError(
            "OpenAI rate limit reached. Please wait a moment and try again."
        ) from exc
    if "timeout" in error_str or "timed out" in error_str:
        raise AIGenerationError(
            "The request to OpenAI timed out. Check your connection and retry."
        ) from exc
    if "authentication" in error_str or "api key" in error_str or "401" in error_str:
        raise AIGenerationError(
            "OpenAI authentication failed. Verify that OPENAI_API_KEY is correct."
        ) from exc
    raise AIGenerationError(f"OpenAI API error during report generation: {exc}") from exc


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a senior coatings assessment specialist with deep expertise in industrial "
    "protective coatings, corrosion science, and facilities maintenance. You hold "
    "certifications from AMPP (formerly SSPC/NACE) and are fluent in ICRI concrete "
    "surface preparation standards. You are thoroughly familiar with Sherwin-Williams "
    "PCG product lines including Macropoxy, Tile-Clad, Waterbased Epoxies, Urethane "
    "topcoats, Resuflor flooring systems, Zinc Clad, and specialty concrete coatings.\n\n"
    "When authoring reports:\n"
    "- Use formal, professional language appropriate for client-facing documents.\n"
    "- Reference specific AMPP surface preparation standards (SSPC-SP 6, SP 10, SP 13, etc.).\n"
    "- Reference ICRI guidelines (ICRI 310.2R) where concrete substrates are present.\n"
    "- Cite specific product data sheet (PDS) parameters: DFT ranges, coverage rates, "
    "overcoat windows, application temperature ranges, mixing ratios.\n"
    "- Draw on Sherwin-Williams manufacturer published literature for all product specs.\n"
    "- Qualify observations with appropriate uncertainty language when visual evidence "
    "alone is insufficient to confirm a diagnosis.\n"
    "- Structure all outputs exactly as requested without adding unsolicited sections."
)


# ---------------------------------------------------------------------------
# Online product research
# ---------------------------------------------------------------------------

def _web_research_coating_system(client, coating_system: str) -> str:
    """
    Research the specified coating system online using OpenAI Responses API web search.
    Returns research text on success, empty string if web search is unavailable.
    """
    if not coating_system.strip():
        return ""
    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search_preview"}],
            input=(
                "Search the Sherwin-Williams website for product data sheet specifications "
                "for this coating system. For each product provide: DFT ranges, coverage "
                "rates per gallon, application temperature window, recoat window, mixing "
                "ratio, and the direct PDS URL on sherwin-williams.com. "
                "Coating system to research:\n\n" + coating_system
            ),
        )
        text = getattr(response, "output_text", "") or ""
        if text:
            logger.info("Web research succeeded for coating system.")
        return text
    except Exception as exc:
        logger.info(
            "OpenAI web search not available (%s) — using model training knowledge.", exc
        )
        return ""


# ---------------------------------------------------------------------------
# Per-photo vision analysis
# ---------------------------------------------------------------------------

_PHOTO_ANALYSIS_PROMPT = (
    "Analyze this site photograph from a facility coating assessment. "
    "Provide a structured failure analysis:\n\n"
    "1. **Failure Type(s):** Visible coating failure modes (delamination, blistering, "
    "rust-through, chalking, cracking, erosion, wear, biological growth).\n"
    "2. **Affected Substrate:** Describe the substrate (carbon steel, galvanized steel, "
    "concrete, masonry, wood).\n"
    "3. **Estimated Severity:** Light, Moderate, or Severe — briefly justify.\n"
    "4. **Surface Contamination Indicators:** Visible contamination (oil, salts, moisture, "
    "efflorescence, rust staining).\n"
    "5. **Recommended Action:** Corrective action implied by the observed condition.\n\n"
    "If the image is unclear or does not show coating conditions, state that clearly. "
    "Be concise and factual."
)


def _analyze_photo(client: Any, uploaded_file) -> str:
    b64 = _encode_image(uploaded_file)
    media_type = _image_media_type(uploaded_file)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{b64}",
                        "detail": "high",
                    },
                },
                {"type": "text", "text": _PHOTO_ANALYSIS_PROMPT},
            ],
        },
    ]
    try:
        return _call_with_fallback(client, messages, max_tokens=1500)
    except AIGenerationError:
        raise
    except Exception as exc:
        _translate_api_error(exc)


# ---------------------------------------------------------------------------
# Consolidated narrative generation
# ---------------------------------------------------------------------------

def _build_narrative_prompt(
    facility_name: str,
    client_name: str,
    apm_name: str,
    coating_system: str,
    photo_findings: list[tuple[str, str]],
    web_research: str = "",
) -> str:
    findings_block = (
        "\n\n".join(f"--- {label} ---\n{analysis}" for label, analysis in photo_findings)
        if photo_findings
        else "No photographs were submitted for this assessment."
    )

    coating_block = coating_system.strip() if coating_system.strip() else (
        "No coating system specification was provided. Recommend an appropriate "
        "SW PCG system based on the observed substrate conditions and failure modes."
    )

    web_block = (
        f"\n\n## Online Product Research (Sherwin-Williams manufacturer data)\n\n{web_research}"
        if web_research else ""
    )

    return f"""You are authoring a formal Site Assessment Report for the following engagement:

**Facility Name:** {facility_name}
**Client / Owner:** {client_name}
**APM Name:** {apm_name}
**Assessment Date:** {date.today().isoformat()}

---

## Per-Photo Failure Analysis Findings

{findings_block}

---

## Recommended Coating System (as provided by APM)

{coating_block}{web_block}

---

## Instructions

Write a complete, professionally formatted Site Assessment Report containing exactly the following eight sections in order. Use the exact section headings specified.

### 1. Introduction / Executive Summary
Write 2-3 paragraphs:
- Identify the facility and client
- Summarize the overall coating condition observed in the photos
- State the purpose and scope of the assessment
- Note the assessment date and APM name

Then on its own line output exactly:
CALLOUT: Assessment basis: This report is based on visual review of the provided photographs only. No destructive testing, moisture testing, adhesion testing, or field sounding was performed as part of this desktop assessment. Final scope, repair depth, and product selection should be confirmed during preconstruction evaluation.

### 2. Existing Conditions and Observed Distress
For each observed condition output one line in this exact format:
CONDITION: <short condition description> | NOTE: <assessment note explaining significance>

List 4-7 condition/note pairs based on the photo findings.

Then on its own line output:
FAILURE_DRIVERS: <1-2 sentence summary of the most probable failure contributors>

### 3. Observed Failure Analysis
Output 4-6 observation bullet points, each on its own line:
BULLET: <complete, specific observation sentence referencing photo evidence>

Then on its own line output:
CALLOUT: <practical implication — what happens if the failure mode is not corrected>

### 4. Surface Preparation Requirements (AMPP and ICRI Basis)
Write a narrative paragraph citing applicable AMPP (SSPC-SP) and ICRI standards for the observed substrate types. Then provide 5-7 specific preparation requirements, each starting with "- ".

### 5. Proposed Recommended Coating System
Output: SYSTEM_NAME: <full system name as it would appear in a specification>

Write 2-3 paragraphs describing the system composition, suitability for the observed conditions, and key performance characteristics drawn from SW manufacturer literature and PDS data.

For each coat in the sequence output one line:
COAT: <layer name> | PRODUCT: <product name, DFT range, coverage rate, and critical PDS parameters> | REASON: <why this layer is specified for these conditions>

Then on its own line output:
PERF_NOTES: <system performance data from SW manufacturer literature: compressive strength, bond strength, abrasion resistance, or other published physical properties>

### 6. Installation Notes and Precautions
Output 5-8 specific, actionable installation precautions, each starting with "- ".

### 7. Conclusion
Write 2-3 paragraphs covering:
- The recommended remediation path forward
- Expected performance benefits
- Any conditions requiring urgent attention

Then on its own line output:
CALLOUT: This assessment is intended as a professional shareable summary for discussion and planning. Final scope, repair extents, moisture considerations, and installation sequencing should be verified in the field before work begins.

### 8. Technical Reference Basis
List all Sherwin-Williams product documents and industry standards referenced in this report. Each on its own line:
REF: <full citation: document title, issuer, issue date or access date>

Write in formal, client-facing language. Do not include any sections other than the eight listed above."""


def _generate_narrative(
    client: Any,
    facility_name: str,
    client_name: str,
    apm_name: str,
    coating_system: str,
    photo_findings: list[tuple[str, str]],
    web_research: str = "",
) -> str:
    user_prompt = _build_narrative_prompt(
        facility_name=facility_name,
        client_name=client_name,
        apm_name=apm_name,
        coating_system=coating_system,
        photo_findings=photo_findings,
        web_research=web_research,
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        return _call_with_fallback(client, messages, max_tokens=8000)
    except AIGenerationError:
        raise
    except Exception as exc:
        _translate_api_error(exc)


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def _extract_section(narrative: str, heading: str, next_headings: list[str]) -> str:
    import re
    escaped = re.escape(heading)
    for next_h in next_headings:
        esc_next = re.escape(next_h)
        bounded = (
            rf"(?:#+\s*\d+\.\s*)?{escaped}[^\n]*\n"
            rf"(.*?)(?=(?:#+\s*\d+\.\s*)?{esc_next})"
        )
        m = re.search(bounded, narrative, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
    pattern = rf"(?:#+\s*\d+\.\s*)?{escaped}[^\n]*\n(.*?)(?=(?:#+\s*\d+\.)|$)"
    m = re.search(pattern, narrative, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_callouts(text: str) -> list[str]:
    import re
    return [
        m.group(1).strip()
        for m in re.finditer(r"^CALLOUT:\s*(.+)$", text, re.MULTILINE)
    ]


def _strip_markers(text: str) -> str:
    import re
    return re.sub(
        r"^(CALLOUT|BULLET|CONDITION|NOTE|FAILURE_DRIVERS|SYSTEM_NAME|PERF_NOTES|COAT|REF):.*$",
        "", text, flags=re.MULTILINE,
    ).strip()


def _parse_executive_summary(narrative: str) -> tuple[str, str]:
    section = _extract_section(
        narrative,
        "Introduction / Executive Summary",
        ["Existing Conditions", "Observed Failure Analysis", "Surface Preparation",
         "Proposed Recommended Coating System", "Installation Notes", "Conclusion",
         "Technical Reference"],
    )
    callouts = _extract_callouts(section)
    clean = _strip_markers(section)
    return clean, (callouts[0] if callouts else "")


def _parse_existing_conditions(narrative: str) -> tuple[list[dict], str]:
    import re
    section = _extract_section(
        narrative,
        "Existing Conditions",
        ["Observed Failure Analysis", "Surface Preparation",
         "Proposed Recommended Coating System", "Installation Notes",
         "Conclusion", "Technical Reference"],
    )
    conditions = []
    pattern = re.compile(r"CONDITION:\s*(.+?)\s*\|\s*NOTE:\s*(.+)", re.IGNORECASE)
    for line in section.splitlines():
        m = pattern.search(line)
        if m:
            conditions.append({"condition": m.group(1).strip(), "note": m.group(2).strip()})

    if not conditions:
        for line in section.splitlines():
            line = line.strip().lstrip("-•*").strip()
            if len(line) > 10 and not line.startswith("FAILURE"):
                parts = re.split(r"\s+[-–]\s+|:\s+", line, maxsplit=1)
                if len(parts) == 2:
                    conditions.append({"condition": parts[0].strip(), "note": parts[1].strip()})
                elif parts:
                    conditions.append({"condition": parts[0].strip(), "note": ""})

    fd = re.search(r"^FAILURE_DRIVERS:\s*(.+)$", section, re.MULTILINE | re.IGNORECASE)
    return conditions, (fd.group(1).strip() if fd else "")


def _parse_failure_analysis(narrative: str) -> tuple[str, str]:
    import re
    section = _extract_section(
        narrative,
        "Observed Failure Analysis",
        ["Surface Preparation", "Proposed Recommended Coating System",
         "Recommended Coating System", "Installation Notes", "Conclusion",
         "Technical Reference"],
    )
    bullets = [
        m.group(1).strip()
        for m in re.finditer(r"^BULLET:\s*(.+)$", section, re.MULTILINE)
    ]
    callouts = _extract_callouts(section)
    bullets_text = (
        "\n".join(f"• {b}" for b in bullets)
        if bullets
        else _strip_markers(section)
    )
    return bullets_text, (callouts[0] if callouts else "")


def _parse_surface_preparation(narrative: str) -> str:
    return _extract_section(
        narrative,
        "Surface Preparation Requirements",
        ["Proposed Recommended Coating System", "Recommended Coating System",
         "Installation Notes", "Conclusion", "Technical Reference"],
    )


def _parse_coating_system(coating_system_input: str, narrative: str) -> tuple[dict, str]:
    import re
    section = _extract_section(
        narrative,
        "Proposed Recommended Coating System",
        ["Installation Notes", "Conclusion", "Technical Reference"],
    )
    if not section:
        section = _extract_section(
            narrative,
            "Recommended Coating System",
            ["Installation Notes", "Conclusion", "Technical Reference"],
        )

    sn = re.search(r"^SYSTEM_NAME:\s*(.+)$", section, re.MULTILINE | re.IGNORECASE)
    system_name = (
        sn.group(1).strip() if sn
        else (coating_system_input.splitlines()[0].strip() if coating_system_input.strip()
              else "See Assessment Narrative")
    )

    pn = re.search(r"^PERF_NOTES:\s*(.+)$", section, re.MULTILINE | re.IGNORECASE)
    perf_notes = pn.group(1).strip() if pn else ""

    coat_pattern = re.compile(
        r"COAT:\s*(.+?)\s*\|\s*PRODUCT:\s*(.+?)\s*\|\s*REASON:\s*(.+)",
        re.IGNORECASE,
    )
    coat_sequence = []
    for line in section.splitlines():
        m = coat_pattern.search(line)
        if m:
            coat_sequence.append({
                "coat": m.group(1).strip(),
                "product": m.group(2).strip(),
                "reason": m.group(3).strip(),
            })

    description = _strip_markers(section)

    return {
        "name": system_name,
        "description": description,
        "coat_sequence": coat_sequence,
        "pds_references": [],
    }, perf_notes


def _parse_installation_notes(narrative: str) -> list[str]:
    section = _extract_section(
        narrative,
        "Installation Notes",
        ["Conclusion", "Technical Reference"],
    )
    notes = []
    for line in section.splitlines():
        line = line.strip().lstrip("-•*").strip()
        if len(line) > 5:
            notes.append(line)
    return notes


def _parse_conclusion(narrative: str) -> tuple[str, str]:
    section = _extract_section(
        narrative,
        "Conclusion",
        ["Technical Reference"],
    )
    callouts = _extract_callouts(section)
    clean = _strip_markers(section)
    return clean, (callouts[0] if callouts else "")


def _parse_technical_references(narrative: str) -> list[str]:
    import re
    section = _extract_section(narrative, "Technical Reference Basis", [])
    if not section:
        section = _extract_section(narrative, "Technical Reference", [])
    refs = []
    for line in section.splitlines():
        line = line.strip()
        m = re.match(r"^REF:\s*(.+)$", line, re.IGNORECASE)
        if m:
            refs.append(m.group(1).strip())
        elif line.startswith(("•", "-", "*")):
            text = line.lstrip("•-* ").strip()
            if len(text) > 5:
                refs.append(text)
    return refs


def _parse_standards_from_narrative(narrative: str) -> list[dict]:
    import re
    standards = []
    seen: set[str] = set()
    patterns = [
        (r"SSPC[- ]SP[ -]?(\w+)", "SSPC-SP {n}", "AMPP Surface Preparation Standard"),
        (r"ICRI[ -]?(\d{3}(?:\.\d+)?[A-Z]?)", "ICRI {n}", "ICRI Surface Preparation Guideline"),
        (r"NACE[ -]?No\.?[ -]?(\d+)", "NACE No.{n}", "NACE Corrosion Control Standard"),
    ]
    sspc_names = {
        "1": "SSPC-SP 1 — Solvent Cleaning",
        "2": "SSPC-SP 2 — Hand Tool Cleaning",
        "3": "SSPC-SP 3 — Power Tool Cleaning",
        "6": "SSPC-SP 6 — Commercial Blast Cleaning",
        "10": "SSPC-SP 10 — Near-White Blast Cleaning",
        "11": "SSPC-SP 11 — Power Tool Cleaning to Bare Metal",
        "13": "SSPC-SP 13 — Surface Preparation of Concrete",
        "14": "SSPC-SP 14 — Industrial Blast Cleaning",
    }
    icri_names = {
        "310": "ICRI 310.2R — Selecting and Specifying Concrete Surface Preparation",
        "310.2": "ICRI 310.2R — Selecting and Specifying Concrete Surface Preparation",
        "310.2R": "ICRI 310.2R — Selecting and Specifying Concrete Surface Preparation",
        "320": "ICRI 320.1 — Concrete Surface Preparation Visual Reference Chips",
    }
    for regex, tmpl, default in patterns:
        for m in re.finditer(regex, narrative, re.IGNORECASE):
            n = m.group(1)
            designation = tmpl.format(n=n)
            if designation in seen:
                continue
            seen.add(designation)
            if "SSPC" in designation:
                name = sspc_names.get(n, f"SSPC-SP {n} — Surface Preparation Standard")
            elif "ICRI" in designation:
                name = icri_names.get(n, f"ICRI {n} — Concrete Surface Preparation")
            else:
                name = default
            standards.append({"designation": designation, "name": name, "applicability": ""})
    return standards


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_site_assessment(
    facility_name: str,
    client_name: str,
    apm_name: str,
    photos: list,
    coating_system: str,
) -> dict:
    """
    Generate a complete site assessment from APM intake-form inputs.

    Returns a content dict matching the schema expected by pdf_builder.build_pdf().
    Raises AIGenerationError on any unrecoverable failure.
    """
    client = _get_client()

    # Step 1: Research coating system online
    web_research = _web_research_coating_system(client, coating_system)

    # Step 2: Per-photo vision analysis
    photo_findings: list[tuple[str, str]] = []
    photo_entries: list[dict] = []

    for i, photo_file in enumerate(photos, start=1):
        label = f"Photo {i}"
        try:
            caption = _analyze_photo(client, photo_file)
        except AIGenerationError as ai_exc:
            # Auth, rate-limit, and config failures should still abort; surface
            # them to the caller. Per-photo issues (content policy, network blip,
            # corrupt image) are logged and replaced with a placeholder so the
            # rest of the report can still be generated.
            err_msg = str(ai_exc).lower()
            if any(t in err_msg for t in ("authentication", "api key", "rate limit")):
                raise
            logger.warning("Photo %d analysis failed: %s — substituting placeholder.", i, ai_exc)
            caption = (
                f"_Automated analysis was unavailable for this photo "
                f"({getattr(photo_file, 'name', 'unknown')}). "
                f"Please review the image directly and edit this caption._"
            )
        except Exception as exc:
            logger.warning("Photo %d analysis raised unexpected error: %s", i, exc)
            caption = (
                f"_Automated analysis encountered an unexpected error for this photo "
                f"({getattr(photo_file, 'name', 'unknown')}). "
                f"Please review the image directly and edit this caption._"
            )
        photo_findings.append((label, caption))
        photo_entries.append({"file_path": "", "caption": caption})

    # Step 3: Consolidated narrative
    try:
        narrative = _generate_narrative(
            client=client,
            facility_name=facility_name,
            client_name=client_name,
            apm_name=apm_name,
            coating_system=coating_system,
            photo_findings=photo_findings,
            web_research=web_research,
        )
    except AIGenerationError:
        raise
    except Exception as exc:
        raise AIGenerationError(
            f"Failed to generate consolidated assessment narrative: {exc}"
        ) from exc

    # Step 4: Parse all sections
    executive_summary, exec_callout = _parse_executive_summary(narrative)
    if not executive_summary:
        paragraphs = [p.strip() for p in narrative.split("\n\n") if p.strip()]
        executive_summary = "\n\n".join(paragraphs[:2]) if paragraphs else narrative[:1000]

    existing_conditions, failure_drivers = _parse_existing_conditions(narrative)
    failure_analysis, failure_callout = _parse_failure_analysis(narrative)
    surface_preparation = _parse_surface_preparation(narrative)
    coating_system_dict, perf_notes = _parse_coating_system(coating_system, narrative)
    installation_notes = _parse_installation_notes(narrative)
    conclusion, conclusion_callout = _parse_conclusion(narrative)
    technical_references = _parse_technical_references(narrative)
    standards = _parse_standards_from_narrative(narrative)

    return {
        "facility_name": facility_name,
        "client_name": client_name,
        "apm_name": apm_name,
        "assessment_date": date.today().isoformat(),
        "executive_summary": executive_summary,
        "exec_summary_callout": exec_callout,
        "_full_narrative": narrative,
        "existing_conditions": existing_conditions,
        "failure_drivers": failure_drivers,
        "photos": photo_entries,
        "failure_analysis": failure_analysis,
        "failure_analysis_callout": failure_callout,
        "surface_preparation": surface_preparation,
        "coating_system": coating_system_dict,
        "coating_system_perf_notes": perf_notes,
        "standards": standards,
        "installation_notes": installation_notes,
        "conclusion": conclusion,
        "conclusion_callout": conclusion_callout,
        "technical_references": technical_references,
        "appendix_items": [],
    }
