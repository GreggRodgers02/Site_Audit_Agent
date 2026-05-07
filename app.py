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

import hashlib
import os

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
# Auth gate — reads APP_PASSWORD_HASH from st.secrets or environment.
# If the variable is absent the app runs without a password (local dev).
# To rotate: update APP_PASSWORD_HASH, restart the service.
# Generate a hash:  python -c "import hashlib; print(hashlib.sha256(b'yourpw').hexdigest())"
# ---------------------------------------------------------------------------
def _get_stored_hash() -> str:
    try:
        return st.secrets.get("APP_PASSWORD_HASH", "") or ""
    except Exception:
        return os.environ.get("APP_PASSWORD_HASH", "")


_stored_hash = _get_stored_hash()
if _stored_hash and not st.session_state.get("authenticated"):
    st.title("Site Audit Agent")
    st.markdown("**Sherwin-Williams PCG Asset Protection** — please log in to continue.")
    st.divider()
    with st.form("login_form"):
        _pw = st.text_input("Password", type="password")
        _login_btn = st.form_submit_button("Log In", type="primary")
    if _login_btn:
        if hashlib.sha256(_pw.encode()).hexdigest() == _stored_hash:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------
def _import_generator():
    from src.ai_generator import generate_site_assessment, AIGenerationError
    return generate_site_assessment, AIGenerationError


def _import_change_request():
    from src.ai_generator import apply_change_request, AIGenerationError
    return apply_change_request, AIGenerationError


def _import_pdf_builder():
    from src.pdf_builder import build_pdf, PDFBuildError
    return build_pdf, PDFBuildError


def _import_preview_builder():
    from src.pdf_builder import render_preview_html, PDFBuildError
    return render_preview_html, PDFBuildError


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
        pds = c.get("pds_url", "").strip()
        base = f"{c.get('coat', '')} | {c.get('product', '')} | {c.get('reason', '')}"
        lines.append(f"{base} | {pds}" if pds else base)
    return "\n".join(lines)


def _text_to_coat_sequence(text: str) -> list[dict]:
    coats = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" | ", 3)
        coats.append({
            "coat": parts[0].strip() if len(parts) > 0 else "",
            "product": parts[1].strip() if len(parts) > 1 else "",
            "reason": parts[2].strip() if len(parts) > 2 else "",
            "pds_url": parts[3].strip() if len(parts) > 3 else "",
        })
    return coats


def _lines_to_list(text: str) -> list[str]:
    return [
        ln.strip().lstrip("•-* ").strip()
        for ln in text.splitlines()
        if ln.strip()
    ]


def _encode_logo_upload(uf) -> str:
    """Convert a Streamlit UploadedFile to a base64 data URI for the PDF template."""
    import base64
    uf.seek(0)
    raw = uf.read()
    name = getattr(uf, "name", "").lower()
    mime = "image/png" if name.endswith(".png") else "image/jpeg"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _encode_photo_upload(uf) -> str:
    """Encode a site photo upload to a base64 JPEG data URI, normalising colour mode and size."""
    from io import BytesIO
    import base64
    from PIL import Image
    uf.seek(0)
    img = Image.open(BytesIO(uf.read()))
    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if w > 960:
        img = img.resize((960, int(h * 960 / w)), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=75, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _current_sections_for_ai() -> dict:
    """Assemble current editable section content for AI change requests."""
    return {k: st.session_state.get(k, "") for k in (
        "ed_exec_summary", "ed_exec_callout", "ed_conditions", "ed_failure_drivers",
        "ed_failure_analysis", "ed_failure_callout", "ed_surface_prep", "ed_coating_name",
        "ed_coating_desc", "ed_coat_sequence", "ed_perf_notes", "ed_install_notes",
        "ed_conclusion", "ed_conclusion_callout", "ed_tech_refs",
    )}


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

    # Merge pre-encoded photo data URIs (cached after generation) into photo entries
    _photos_raw = result.get("photos", [])
    _photos_encoded = st.session_state.get("photos_encoded", [])
    _uploaded_ss = st.session_state.get("photos", [])
    _photos = []
    for _i, _p in enumerate(_photos_raw):
        _entry = dict(_p)
        if _i < len(_photos_encoded) and _photos_encoded[_i]:
            _entry["image_data_uri"] = _photos_encoded[_i]
        if not _entry.get("filename") and _i < len(_uploaded_ss):
            _entry["filename"] = getattr(_uploaded_ss[_i], "name", f"Photo {_i + 1}")
        _photos.append(_entry)

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
        "photos": _photos,
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
        "brand_blue": st.session_state.get("brand_blue", "#003DA5") or "#003DA5",
        "brand_red": st.session_state.get("brand_red", "#F5333F") or "#F5333F",
        "logo01_uri_override": (
            _encode_logo_upload(st.session_state["brand_logo1"])
            if st.session_state.get("brand_logo1") else None
        ),
        "logo02_uri_override": (
            _encode_logo_upload(st.session_state["brand_logo2"])
            if st.session_state.get("brand_logo2") else None
        ),
    }


# ---------------------------------------------------------------------------
# Sidebar — Branding, auth controls, Past Reports
# ---------------------------------------------------------------------------
with st.sidebar:

    # -- Branding controls --
    with st.expander("Branding", expanded=False):
        st.caption(
            "Customize logos and colors for this session. "
            "Defaults to Sherwin-Williams brand."
        )
        st.file_uploader(
            "Logo 1 (running header)",
            type=["png", "jpg", "jpeg"],
            key="brand_logo1",
            help="Replaces the small header logo on inner pages. PNG recommended.",
        )
        st.file_uploader(
            "Logo 2 (cover page)",
            type=["png", "jpg", "jpeg"],
            key="brand_logo2",
            help="Replaces the large cover-page logo. PNG recommended.",
        )
        st.color_picker("Primary color", value="#003DA5", key="brand_blue")
        st.color_picker("Accent color", value="#F5333F", key="brand_red")

    st.divider()

    # -- Log out --
    if _stored_hash and st.session_state.get("authenticated"):
        if st.button("Log out", key="logout_btn"):
            st.session_state.clear()
            st.rerun()
        st.divider()

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

        # Store photos in session_state before init
        st.session_state["photos"] = uploaded_photos

        # Pre-encode site photos once so preview and PDF both use the cached URIs
        _encoded_uris = []
        for _uf in uploaded_photos:
            try:
                _encoded_uris.append(_encode_photo_upload(_uf))
            except Exception as _enc_err:
                import logging as _log
                _log.getLogger(__name__).warning("Could not pre-encode photo: %s", _enc_err)
                _encoded_uris.append(None)
        st.session_state["photos_encoded"] = _encoded_uris

        # Initialise all editable session_state keys from the fresh result
        _init_edit_state(result)

        # Clear any stale PDF and change history from a prior generation
        for _stale_key in ("pdf_bytes", "pdf_filename", "pdf_saved_to_library", "change_history"):
            st.session_state.pop(_stale_key, None)

        st.success("Assessment generated. Review and edit each section below, then generate your PDF.")
        st.rerun()


# ---------------------------------------------------------------------------
# Preview & Review section  (renders whenever a result exists in session_state)
# ---------------------------------------------------------------------------
if "result" in st.session_state:
    result = st.session_state["result"]

    st.divider()

    _hdr_left, _hdr_right = st.columns([3, 1])
    with _hdr_left:
        st.subheader("Review Generated Assessment")
    with _hdr_right:
        if st.button("⟲ Start Over", key="start_over",
                     help="Clear this assessment and return to the empty form."):
            for _k in list(st.session_state.keys()):
                if _k.startswith("ed_") or _k in (
                    "result", "photos", "photos_encoded",
                    "pdf_bytes", "pdf_filename", "pdf_saved_to_library", "change_history",
                ):
                    st.session_state.pop(_k, None)
            st.rerun()

    # -- Metadata banner --
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Facility", result.get("facility_name", ""))
    col2.metric("Client", result.get("client_name", ""))
    col3.metric("APM", result.get("apm_name", ""))
    col4.metric("Date", result.get("assessment_date", ""))

    st.divider()

    # ---------------------------------------------------------------- #
    # Document preview — rendered from the same Jinja2 template as PDF
    # ---------------------------------------------------------------- #
    st.subheader("Document Preview")
    st.caption(
        "Approximate preview — layout is representative; "
        "final PDF may differ slightly in pagination and margins."
    )

    try:
        _render_preview, _PreviewBuildError = _import_preview_builder()
        _preview_content = _build_pdf_content()
        _preview_html = _render_preview(_preview_content)
        import streamlit.components.v1 as _components
        _components.html(_preview_html, height=960, scrolling=True)
    except Exception as _prev_err:
        st.warning(f"Preview could not be rendered: {_prev_err}")

    st.divider()

    # ---------------------------------------------------------------- #
    # AI change request
    # ---------------------------------------------------------------- #
    st.subheader("Request a Change")
    st.caption(
        "Describe any change in plain English — the AI will update the relevant sections "
        "and the preview above will refresh automatically."
    )

    with st.form("change_request_form", clear_on_submit=True):
        _change_text = st.text_input(
            "What would you like to change?",
            placeholder=(
                "e.g., Make the conclusion more concise, "
                "or Add more detail about moisture mitigation in surface prep"
            ),
        )
        _apply_btn = st.form_submit_button("Apply Change", type="primary")

    if _apply_btn and _change_text.strip():
        _apply_fn, _AIGenErr = _import_change_request()
        with st.spinner("Applying change…"):
            try:
                _changes = _apply_fn(_change_text.strip(), _current_sections_for_ai())
                for _ck, _cv in _changes.items():
                    st.session_state[_ck] = _cv
                st.session_state.setdefault("change_history", []).append(_change_text.strip())
                _section_count = len(_changes)
                st.session_state.pop("pdf_bytes", None)
                st.session_state.pop("pdf_filename", None)
                st.success(
                    f"Applied — {_section_count} section(s) updated. "
                    "Preview will refresh on the next rerun."
                )
                st.rerun()
            except _AIGenErr as _ai_e:
                st.error(f"Could not apply change: {_ai_e}")
            except Exception as _unexp:
                st.error(f"Unexpected error applying change: {_unexp}")

    if st.session_state.get("change_history"):
        with st.expander(
            f"Change history — {len(st.session_state['change_history'])} applied",
            expanded=False,
        ):
            for _ci, _ch in enumerate(st.session_state["change_history"], 1):
                st.caption(f"{_ci}. {_ch}")

    st.divider()

    # ---------------------------------------------------------------- #
    # Fine-tune manually — all section text editors (collapsed by default)
    # ---------------------------------------------------------------- #
    with st.expander("Fine-tune manually", expanded=False):
        st.caption(
            "Direct field editors for precise control. "
            "Changes here update the preview and final PDF."
        )

        # Section 1 — Executive Summary
        with st.expander("1. Executive Summary", expanded=False):
            st.text_area("Executive Summary", key="ed_exec_summary", height=200)
            st.text_area("Assessment Basis Callout", key="ed_exec_callout", height=80)

        # Section 2 — Existing Conditions
        with st.expander("2. Existing Conditions", expanded=False):
            st.caption("One per line: **Condition | Note**")
            st.text_area(
                "Existing Conditions",
                key="ed_conditions",
                height=220,
            )
            st.text_area("Likely Failure Drivers", key="ed_failure_drivers", height=80)

        # Section 3 — Photo Log (display-only)
        _uploaded_photos_ss = st.session_state.get("photos", [])
        _photos_data = result.get("photos", [])
        with st.expander(f"3. Photo Log — {len(_photos_data)} photo(s)", expanded=False):
            if _photos_data:
                for _pi, _entry in enumerate(_photos_data, start=1):
                    _pname = (
                        getattr(_uploaded_photos_ss[_pi - 1], "name", "")
                        if _pi - 1 < len(_uploaded_photos_ss) else ""
                    )
                    st.markdown(f"**Photo {_pi}** — {_pname}")
                    if _pi - 1 < len(_uploaded_photos_ss):
                        st.image(_uploaded_photos_ss[_pi - 1], use_container_width=True)
                    st.markdown(f"*AI Caption:* {_entry.get('caption', '')}")
                    if _pi < len(_photos_data):
                        st.divider()
            else:
                st.info("No photos were attached to this assessment.")

        # Section 4 — Failure Analysis
        with st.expander("4. Observed Failure Analysis", expanded=False):
            st.caption("One per line: **• Bullet text**")
            st.text_area("Failure Analysis Bullets", key="ed_failure_analysis", height=200)
            st.text_area("Practical Implication Callout", key="ed_failure_callout", height=80)

        # Section 5 — Surface Preparation
        with st.expander("5. Surface Preparation Requirements", expanded=False):
            st.text_area(
                "Surface Preparation (narrative + bullets)",
                key="ed_surface_prep",
                height=280,
            )

        # Section 6 — Coating System
        with st.expander("6. Recommended Coating System", expanded=False):
            st.text_input("System Name", key="ed_coating_name")
            st.text_area("System Description", key="ed_coating_desc", height=160)
            st.caption(
                "Coat Sequence — one per line: "
                "**Layer | Product & specs | Reason | PDS URL (optional)**"
            )
            st.text_area("Coat Sequence", key="ed_coat_sequence", height=160)
            st.text_area("System Performance Notes", key="ed_perf_notes", height=100)

        # Section 7 — Installation Notes
        with st.expander("7. Installation Notes & Precautions", expanded=False):
            st.caption("One precaution per line.")
            st.text_area("Installation Notes", key="ed_install_notes", height=200)

        # Section 8 — Conclusion
        with st.expander("8. Conclusion", expanded=False):
            st.text_area("Conclusion", key="ed_conclusion", height=180)
            st.text_area("Closing Callout", key="ed_conclusion_callout", height=80)

        # Section 9 — Technical References
        with st.expander("9. Technical Reference Basis", expanded=False):
            st.caption("One reference per line.")
            st.text_area("Technical References", key="ed_tech_refs", height=200)

    st.divider()

    # ---------------------------------------------------------------- #
    # PDF generation
    # ---------------------------------------------------------------- #
    st.subheader("Generate PDF Report")
    st.caption(
        "All edits and AI changes above are included. "
        "Click below to compile and download the branded report."
    )

    try:
        build_pdf, PDFBuildError = _import_pdf_builder()
    except Exception as _pdf_import_exc:
        st.error(f"Failed to load the PDF builder module: {_pdf_import_exc}")
        build_pdf = None
        PDFBuildError = None

    if build_pdf is not None:
        if st.button("Generate PDF Report", type="primary", key="generate_pdf"):
            with st.spinner("Assembling branded PDF… This may take up to 30 seconds."):
                try:
                    pdf_content = _build_pdf_content()
                    pdf_bytes = build_pdf(pdf_content)

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

                    st.session_state["pdf_bytes"] = pdf_bytes
                    st.session_state["pdf_filename"] = _pdf_filename

                except PDFBuildError as pdf_err:
                    st.error(f"PDF generation failed: {pdf_err}")
                except Exception as unexpected_pdf_err:
                    st.error(f"Unexpected error building PDF: {unexpected_pdf_err}")

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
