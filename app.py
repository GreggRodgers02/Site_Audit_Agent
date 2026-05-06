"""
app.py
------
Site Audit Agent — Streamlit entry point.

Multi-step flow:
  1. Intake form  — APM fills in facility/client info, uploads photos, optionally
                    pastes a coating system name.
  2. Generation   — AI pipeline runs; result stored in st.session_state.
  3. Review/Edit  — APM reviews every section and edits as needed.
  4. PDF export   — Generate PDF from the (edited) content; download button appears
                    at the bottom of the review section.
"""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Document library
# ---------------------------------------------------------------------------
try:
    from src.document_library import (
        init_db as _init_db,
        save_report as _save_report,
        search_reports as _search_reports,
        delete_report as _delete_report,
        build_report_filename as _build_report_filename,
    )
    _init_db()
    _LIBRARY_AVAILABLE = True
except Exception as _lib_init_err:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "Document library unavailable: %s", _lib_init_err
    )
    _LIBRARY_AVAILABLE = False

# ---------------------------------------------------------------------------
# Page config — must be the first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Site Audit Agent",
    page_icon=None,
    layout="centered",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------
def _import_generator():
    from src.ai_generator import generate_site_assessment, AIGenerationError
    return generate_site_assessment, AIGenerationError


def _import_pdf_builder():
    from src.pdf_builder import build_pdf, PDFBuildError
    return build_pdf, PDFBuildError


# ---------------------------------------------------------------------------
# Helpers for serialising list fields to editable text and back
# ---------------------------------------------------------------------------

def _conditions_to_text(conditions: list[dict]) -> str:
    lines = []
    for c in conditions:
        cond = c.get("condition", "")
        note = c.get("note", "")
        lines.append(f"{cond} | {note}" if note else cond)
    return "\n".join(lines)


def _text_to_conditions(text: str) -> list[dict]:
    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" | ", 1)
        result.append(
            {"condition": parts[0].strip(), "note": parts[1].strip()}
            if len(parts) == 2
            else {"condition": parts[0].strip(), "note": ""}
        )
    return result


def _coat_sequence_to_text(coats: list[dict]) -> str:
    lines = []
    for c in coats:
        lines.append(
            f"{c.get('coat', '')} | {c.get('product', '')} | {c.get('reason', '')}"
        )
    return "\n".join(lines)


def _text_to_coat_sequence(text: str) -> list[dict]:
    coats = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" | ", 2)
        coats.append({
            "coat": parts[0].strip() if len(parts) > 0 else "",
            "product": parts[1].strip() if len(parts) > 1 else "",
            "reason": parts[2].strip() if len(parts) > 2 else "",
        })
    return coats


def _lines_to_list(text: str) -> list[str]:
    return [
        ln.strip().lstrip("•-* ").strip()
        for ln in text.splitlines()
        if ln.strip()
    ]


# ---------------------------------------------------------------------------
# Session state initialisation — called once per new generation result
# ---------------------------------------------------------------------------

def _init_edit_state(result: dict) -> None:
    """Populate session_state edit keys from a freshly generated result dict."""
    st.session_state["result"] = result

    st.session_state["ed_exec_summary"] = result.get("executive_summary", "")
    st.session_state["ed_exec_callout"] = result.get("exec_summary_callout", "")

    st.session_state["ed_conditions"] = _conditions_to_text(
        result.get("existing_conditions", [])
    )
    st.session_state["ed_failure_drivers"] = result.get("failure_drivers", "")

    st.session_state["ed_failure_analysis"] = result.get("failure_analysis", "")
    st.session_state["ed_failure_callout"] = result.get("failure_analysis_callout", "")

    st.session_state["ed_surface_prep"] = result.get("surface_preparation", "")

    cs = result.get("coating_system", {})
    st.session_state["ed_coating_name"] = cs.get("name", "")
    st.session_state["ed_coating_desc"] = cs.get("description", "")
    st.session_state["ed_coat_sequence"] = _coat_sequence_to_text(
        cs.get("coat_sequence", [])
    )
    st.session_state["ed_perf_notes"] = result.get("coating_system_perf_notes", "")

    st.session_state["ed_install_notes"] = "\n".join(
        result.get("installation_notes", [])
    )

    st.session_state["ed_conclusion"] = result.get("conclusion", "")
    st.session_state["ed_conclusion_callout"] = result.get("conclusion_callout", "")

    st.session_state["ed_tech_refs"] = "\n".join(
        result.get("technical_references", [])
    )


# ---------------------------------------------------------------------------
# Build the final content dict from edited session state (for PDF generation)
# ---------------------------------------------------------------------------

def _build_pdf_content() -> dict:
    result = st.session_state.get("result", {})

    return {
        "facility_name": result.get("facility_name", ""),
        "client_name": result.get("client_name", ""),
        "apm_name": result.get("apm_name", ""),
        "assessment_date": result.get("assessment_date", ""),
        "executive_summary": st.session_state.get("ed_exec_summary", ""),
        "exec_summary_callout": st.session_state.get("ed_exec_callout", ""),
        "existing_conditions": _text_to_conditions(
            st.session_state.get("ed_conditions", "")
        ),
        "failure_drivers": st.session_state.get("ed_failure_drivers", ""),
        "photos": result.get("photos", []),
        "failure_analysis": st.session_state.get("ed_failure_analysis", ""),
        "failure_analysis_callout": st.session_state.get("ed_failure_callout", ""),
        "surface_preparation": st.session_state.get("ed_surface_prep", ""),
        "coating_system": {
            "name": st.session_state.get("ed_coating_name", ""),
            "description": st.session_state.get("ed_coating_desc", ""),
            "coat_sequence": _text_to_coat_sequence(
                st.session_state.get("ed_coat_sequence", "")
            ),
            "pds_references": [],
        },
        "coating_system_perf_notes": st.session_state.get("ed_perf_notes", ""),
        "standards": result.get("standards", []),
        "installation_notes": _lines_to_list(
            st.session_state.get("ed_install_notes", "")
        ),
        "conclusion": st.session_state.get("ed_conclusion", ""),
        "conclusion_callout": st.session_state.get("ed_conclusion_callout", ""),
        "technical_references": _lines_to_list(
            st.session_state.get("ed_tech_refs", "")
        ),
        "appendix_items": [],
    }


# ---------------------------------------------------------------------------
# Past Reports sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("📋 Past Reports")

    if not _LIBRARY_AVAILABLE:
        st.warning("Document library unavailable. Report saving and history are disabled.")
    else:
        _search_query = st.text_input(
            "Search by client or facility",
            key="lib_search_query",
            placeholder="Type to filter...",
        )
        _col_from, _col_to = st.columns(2)
        with _col_from:
            _date_from = st.date_input("From", value=None, key="lib_date_from", format="YYYY-MM-DD")
        with _col_to:
            _date_to = st.date_input("To", value=None, key="lib_date_to", format="YYYY-MM-DD")

        _date_from_str = _date_from.isoformat() if _date_from else None
        _date_to_str = _date_to.isoformat() if _date_to else None

        try:
            if _search_query.strip():
                _by_client = _search_reports(
                    client_name=_search_query.strip(),
                    date_from=_date_from_str, date_to=_date_to_str,
                )
                _by_facility = _search_reports(
                    facility_name=_search_query.strip(),
                    date_from=_date_from_str, date_to=_date_to_str,
                )
                _seen_ids: set[int] = set()
                _merged: list[dict] = []
                for _rec in _by_client + _by_facility:
                    if _rec["id"] not in _seen_ids:
                        _seen_ids.add(_rec["id"])
                        _merged.append(_rec)
                _results = sorted(
                    _merged, key=lambda r: r.get("date_generated", ""), reverse=True
                )
            else:
                _results = _search_reports(date_from=_date_from_str, date_to=_date_to_str)
        except Exception as _search_err:
            st.error(f"Could not load past reports: {_search_err}")
            _results = []

        _results = _results[:50]

        if not _results:
            st.caption("No reports found.")
        else:
            st.caption(f"{len(_results)} report(s) found.")
            st.divider()

            for _report in _results:
                import os as _os
                from pathlib import Path as _Path

                _rid = _report["id"]
                _r_client = _report.get("client_name", "")
                _r_facility = _report.get("facility_name", "")
                _r_apm = _report.get("apm_name", "")
                _r_date = _report.get("date_generated", "")[:10]
                _r_file_path = _report.get("file_path", "")
                _abs_path = _Path(__file__).parent / _r_file_path

                st.markdown(f"**{_r_client}**")
                st.caption(f"{_r_facility} | {_r_date} | APM: {_r_apm}")

                _file_exists = _abs_path.exists() if _r_file_path else False

                if _file_exists:
                    try:
                        with open(_abs_path, "rb") as _fh:
                            _pdf_bytes = _fh.read()
                        st.download_button(
                            label="Download",
                            data=_pdf_bytes,
                            file_name=_Path(_r_file_path).name,
                            mime="application/pdf",
                            key=f"dl_{_rid}",
                        )
                    except Exception:
                        st.error("Could not read report file.")
                else:
                    st.caption("⚠ File unavailable")

                _confirm_key = f"confirm_delete_{_rid}"
                if st.button("Delete", key=f"del_{_rid}", type="secondary"):
                    st.session_state[_confirm_key] = True

                if st.session_state.get(_confirm_key, False):
                    st.warning("Are you sure? This cannot be undone.")
                    _ccol1, _ccol2 = st.columns(2)
                    with _ccol1:
                        if st.button("Confirm Delete", key=f"confirm_{_rid}", type="primary"):
                            _delete_report(_rid)
                            st.session_state.pop(_confirm_key, None)
                            st.rerun()
                    with _ccol2:
                        if st.button("Cancel", key=f"cancel_{_rid}"):
                            st.session_state.pop(_confirm_key, None)
                            st.rerun()

                st.divider()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Site Audit Agent")
st.markdown(
    "**Sherwin-Williams PCG Asset Protection** — "
    "Generate a professional site assessment report from field photos and coating specifications."
)
st.divider()

# ---------------------------------------------------------------------------
# Intake form
# ---------------------------------------------------------------------------
st.subheader("Intake Form")

with st.form("intake_form"):
    st.markdown("#### Facility & Client Information")

    facility_name = st.text_input(
        label="Facility Name",
        placeholder="e.g., Acme Manufacturing — Building 4",
    )
    client_name = st.text_input(
        label="Client Name",
        placeholder="e.g., Acme Corporation",
    )
    apm_name = st.text_input(
        label="APM Name",
        placeholder="e.g., Jane Smith",
    )

    st.markdown("#### Site Photographs")
    uploaded_photos = st.file_uploader(
        label="Upload Site Photos",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        help="Upload all photographs taken during the site visit. JPG and PNG accepted.",
    )

    st.markdown("#### Coating System")
    coating_system = st.text_input(
        label="Coating System Name (optional)",
        placeholder="e.g., Sherwin-Williams Resuflor Guard SL with Resutile AT topcoat",
        help=(
            "Enter the coating system name or key product names. "
            "The AI will research the product specs online."
        ),
    )

    submit_button = st.form_submit_button(label="Generate Report", type="primary")

# ---------------------------------------------------------------------------
# Validation and generation
# ---------------------------------------------------------------------------
if submit_button:
    validation_errors = []
    if not facility_name.strip():
        validation_errors.append("Facility Name is required.")
    if not client_name.strip():
        validation_errors.append("Client Name is required.")
    if not apm_name.strip():
        validation_errors.append("APM Name is required.")
    if not uploaded_photos:
        validation_errors.append("At least one site photograph is required.")

    if validation_errors:
        for msg in validation_errors:
            st.error(msg)
    else:
        try:
            generate_site_assessment, AIGenerationError = _import_generator()
        except Exception as import_exc:
            st.error(f"Failed to load the AI generation module: {import_exc}")
            st.stop()

        with st.spinner(
            "Researching products and analyzing site photos… This may take 60–120 seconds."
        ):
            try:
                result = generate_site_assessment(
                    facility_name=facility_name.strip(),
                    client_name=client_name.strip(),
                    apm_name=apm_name.strip(),
                    photos=uploaded_photos,
                    coating_system=coating_system.strip(),
                )
            except AIGenerationError as ai_err:
                st.error(f"Report generation failed: {ai_err}")
                st.stop()
            except Exception as unexpected_err:
                st.error(f"An unexpected error occurred: {unexpected_err}")
                st.stop()

        # Store photos in session_state before init (used for PDF photo encoding)
        st.session_state["photos"] = uploaded_photos

        # Initialise all editable session_state keys from the fresh result
        _init_edit_state(result)

        # Clear any stale PDF from a prior generation so the download button
        # does not point at the previous report's bytes.
        for _stale_key in ("pdf_bytes", "pdf_filename", "pdf_saved_to_library"):
            st.session_state.pop(_stale_key, None)

        st.success("Assessment generated. Review and edit each section below, then generate your PDF.")
        st.rerun()


# ---------------------------------------------------------------------------
# Review & Edit section  (renders whenever a result exists in session_state)
# ---------------------------------------------------------------------------
if "result" in st.session_state:
    result = st.session_state["result"]

    st.divider()

    _hdr_left, _hdr_right = st.columns([3, 1])
    with _hdr_left:
        st.subheader("Review & Edit Generated Assessment")
    with _hdr_right:
        if st.button("⟲ Start Over", key="start_over", help="Clear this assessment and return to the empty form."):
            for _k in list(st.session_state.keys()):
                if _k.startswith("ed_") or _k in (
                    "result", "photos", "pdf_bytes", "pdf_filename", "pdf_saved_to_library"
                ):
                    st.session_state.pop(_k, None)
            st.rerun()

    st.caption(
        "Each section is pre-populated from the AI. "
        "Edit any field before generating the PDF. Changes are saved automatically."
    )

    # -- Metadata banner --
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Facility", result.get("facility_name", ""))
    col2.metric("Client", result.get("client_name", ""))
    col3.metric("APM", result.get("apm_name", ""))
    col4.metric("Date", result.get("assessment_date", ""))

    st.divider()

    # ---------------------------------------------------------------- #
    # Section 1 — Executive Summary
    # ---------------------------------------------------------------- #
    with st.expander("1. Executive Summary", expanded=True):
        st.text_area(
            "Executive Summary",
            key="ed_exec_summary",
            height=200,
            help="Edit the executive summary as needed.",
        )
        st.text_area(
            "Assessment Basis Callout",
            key="ed_exec_callout",
            height=80,
            help="The callout box that appears below the executive summary in the PDF.",
        )

    # ---------------------------------------------------------------- #
    # Section 2 — Existing Conditions
    # ---------------------------------------------------------------- #
    with st.expander("2. Existing Conditions", expanded=False):
        st.caption(
            "One condition per line in the format: **Condition | Note**"
        )
        st.text_area(
            "Existing Conditions (Condition | Note — one per line)",
            key="ed_conditions",
            height=220,
        )
        st.text_area(
            "Likely Failure Drivers",
            key="ed_failure_drivers",
            height=80,
        )

    # ---------------------------------------------------------------- #
    # Section 3 — Photo Log (display-only; photos can't be re-uploaded here)
    # ---------------------------------------------------------------- #
    uploaded_photos_ss = st.session_state.get("photos", [])
    photos_data = result.get("photos", [])

    with st.expander(f"3. Photo Log — {len(photos_data)} photo(s)", expanded=False):
        if photos_data:
            for i, entry in enumerate(photos_data, start=1):
                st.markdown(f"**Photo {i}** — {getattr(uploaded_photos_ss[i-1], 'name', '') if i-1 < len(uploaded_photos_ss) else ''}")
                if i - 1 < len(uploaded_photos_ss):
                    st.image(
                        uploaded_photos_ss[i - 1],
                        use_container_width=True,
                    )
                st.markdown(f"*AI Caption:* {entry.get('caption', '')}")
                if i < len(photos_data):
                    st.divider()
        else:
            st.info("No photos were attached to this assessment.")

    # ---------------------------------------------------------------- #
    # Section 4 — Observed Failure Analysis
    # ---------------------------------------------------------------- #
    with st.expander("4. Observed Failure Analysis", expanded=False):
        st.caption(
            "Bullet points — one per line, with or without leading bullet character."
        )
        st.text_area(
            "Failure Analysis Bullets",
            key="ed_failure_analysis",
            height=200,
        )
        st.text_area(
            "Practical Implication Callout",
            key="ed_failure_callout",
            height=80,
        )

    # ---------------------------------------------------------------- #
    # Section 5 — Surface Preparation Requirements
    # ---------------------------------------------------------------- #
    with st.expander("5. Surface Preparation Requirements", expanded=False):
        st.text_area(
            "Surface Preparation (narrative + bullets)",
            key="ed_surface_prep",
            height=280,
        )

    # ---------------------------------------------------------------- #
    # Section 6 — Recommended Coating System
    # ---------------------------------------------------------------- #
    with st.expander("6. Recommended Coating System", expanded=False):
        st.text_input(
            "System Name",
            key="ed_coating_name",
            help="e.g., Sherwin-Williams Resuflor Guard SL Self-Leveling Flooring System",
        )
        st.text_area(
            "System Description",
            key="ed_coating_desc",
            height=160,
        )
        st.caption(
            "Coat Sequence — one per line: **Layer | Product & specs | Reason for recommendation**"
        )
        st.text_area(
            "Coat Sequence",
            key="ed_coat_sequence",
            height=160,
            help="Each line: Layer Name | Product Name, DFT/coverage/PDS specs | Reason",
        )
        st.text_area(
            "System Performance Notes",
            key="ed_perf_notes",
            height=100,
            help="Physical property data from SW manufacturer literature.",
        )

    # ---------------------------------------------------------------- #
    # Section 7 — Installation Notes
    # ---------------------------------------------------------------- #
    with st.expander("7. Installation Notes & Precautions", expanded=False):
        st.caption("One precaution per line.")
        st.text_area(
            "Installation Notes",
            key="ed_install_notes",
            height=200,
        )

    # ---------------------------------------------------------------- #
    # Section 8 — Conclusion
    # ---------------------------------------------------------------- #
    with st.expander("8. Conclusion", expanded=False):
        st.text_area(
            "Conclusion",
            key="ed_conclusion",
            height=180,
        )
        st.text_area(
            "Closing Callout",
            key="ed_conclusion_callout",
            height=80,
        )

    # ---------------------------------------------------------------- #
    # Section 9 — Technical Reference Basis
    # ---------------------------------------------------------------- #
    with st.expander("9. Technical Reference Basis", expanded=False):
        st.caption("One reference per line.")
        st.text_area(
            "Technical References",
            key="ed_tech_refs",
            height=200,
        )

    # ---------------------------------------------------------------- #
    # PDF generation — at the bottom of the review section
    # ---------------------------------------------------------------- #
    st.divider()
    st.subheader("Generate PDF Report")
    st.caption(
        "All edits above are included in the PDF. "
        "Click below to compile and download the report."
    )

    try:
        build_pdf, PDFBuildError = _import_pdf_builder()
    except Exception as import_exc:
        st.error(f"Failed to load the PDF builder module: {import_exc}")
        build_pdf = None
        PDFBuildError = None

    if build_pdf is not None:
        if st.button("Generate PDF Report", type="primary", key="generate_pdf"):
            with st.spinner("Assembling branded PDF… This may take up to 30 seconds."):
                try:
                    import base64 as _b64
                    from io import BytesIO as _BytesIO
                    from PIL import Image as _Image

                    def _encode_upload(uf) -> str:
                        uf.seek(0)
                        raw = uf.read()
                        img = _Image.open(_BytesIO(raw))
                        if img.mode in ("RGBA", "P", "LA"):
                            bg = _Image.new("RGB", img.size, (255, 255, 255))
                            if img.mode == "P":
                                img = img.convert("RGBA")
                            bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                            img = bg
                        elif img.mode != "RGB":
                            img = img.convert("RGB")
                        w, h = img.size
                        if w > 960:
                            img = img.resize((960, int(h * 960 / w)), _Image.LANCZOS)
                        buf = _BytesIO()
                        img.save(buf, format="JPEG", quality=75, optimize=True)
                        b64 = _b64.b64encode(buf.getvalue()).decode("ascii")
                        return f"data:image/jpeg;base64,{b64}"

                    pdf_content = _build_pdf_content()

                    # Inject base64-encoded photos into the photo entries
                    photos_for_pdf = [dict(p) for p in pdf_content.get("photos", [])]
                    for idx, uf in enumerate(uploaded_photos_ss):
                        if idx < len(photos_for_pdf):
                            try:
                                photos_for_pdf[idx]["image_data_uri"] = _encode_upload(uf)
                                if not photos_for_pdf[idx].get("filename"):
                                    photos_for_pdf[idx]["filename"] = getattr(uf, "name", f"Photo {idx + 1}")
                            except Exception as _enc_err:
                                import logging as _log
                                _log.getLogger(__name__).warning(
                                    "Could not encode photo %d: %s", idx + 1, _enc_err
                                )
                    pdf_content["photos"] = photos_for_pdf

                    pdf_bytes = build_pdf(pdf_content)

                    # Save to library
                    _pdf_filename = None
                    if _LIBRARY_AVAILABLE:
                        try:
                            from pathlib import Path as _Path
                            _rel_path = _build_report_filename(
                                pdf_content["facility_name"],
                                pdf_content["client_name"],
                            )
                            _abs_pdf_path = _Path(__file__).parent / _rel_path
                            _abs_pdf_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(_abs_pdf_path, "wb") as _pdf_fh:
                                _pdf_fh.write(pdf_bytes)
                            _save_report(
                                facility_name=pdf_content["facility_name"],
                                client_name=pdf_content["client_name"],
                                apm_name=pdf_content["apm_name"],
                                file_path=_rel_path,
                            )
                            st.session_state["pdf_saved_to_library"] = True
                            _pdf_filename = _Path(_rel_path).name
                        except Exception as _lib_save_err:
                            import logging as _log2
                            _log2.getLogger(__name__).warning(
                                "Could not save report to library: %s", _lib_save_err
                            )
                            st.session_state["pdf_saved_to_library"] = False

                    if not _pdf_filename:
                        _safe = "".join(
                            c if c.isalnum() or c in ("-", "_") else "_"
                            for c in pdf_content["facility_name"]
                        )
                        _pdf_filename = (
                            f"SW_SiteAudit_{_safe}_{pdf_content.get('assessment_date', 'today')}.pdf"
                        )

                    # Persist PDF in session state so the download button survives reruns
                    st.session_state["pdf_bytes"] = pdf_bytes
                    st.session_state["pdf_filename"] = _pdf_filename

                except PDFBuildError as pdf_err:
                    st.error(f"PDF generation failed: {pdf_err}")
                except Exception as unexpected_pdf_err:
                    st.error(f"Unexpected error building PDF: {unexpected_pdf_err}")

    # Render download UI whenever a generated PDF exists in session state.
    # This survives reruns (e.g. after the user clicks the download button).
    if st.session_state.get("pdf_bytes"):
        if st.session_state.get("pdf_saved_to_library"):
            st.success("Report saved to library.")
        elif st.session_state.get("pdf_saved_to_library") is False:
            st.warning("PDF generated but could not be saved to library.")

        st.download_button(
            label="⬇ Download PDF Report",
            data=st.session_state["pdf_bytes"],
            file_name=st.session_state.get("pdf_filename", "SW_SiteAudit.pdf"),
            mime="application/pdf",
            key="download_pdf",
        )
        st.success("PDF ready — click above to download.")
