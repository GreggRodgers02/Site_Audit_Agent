"""
pdf_builder.py
--------------
PDF assembly engine for the Site Audit Agent.

Accepts an AI-generated (and APM-edited) content dict and returns raw PDF bytes
suitable for st.download_button().

Public API
----------
build_pdf(content: dict) -> bytes
    Render a fully branded Sherwin-Williams Site Assessment PDF.

PDFBuildError
    Raised on any unrecoverable rendering failure.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import markupsafe

logger = logging.getLogger(__name__)

_ASSETS_DIR = Path(__file__).parent.parent / "assets"
_TEMPLATE_PATH = _ASSETS_DIR / "pdf_template.html"
_LOGO_01_PATH = _ASSETS_DIR / "SW-Logo-01.png"
_LOGO_02_PATH = _ASSETS_DIR / "SW-Logo-02.png"


class PDFBuildError(Exception):
    """Raised when the PDF cannot be rendered."""


def _require_weasyprint():
    try:
        existing = os.environ.get("DYLD_LIBRARY_PATH", "")
        # Apple Silicon Homebrew: /opt/homebrew/lib; Intel Homebrew: /usr/local/lib
        for lib_path in ("/opt/homebrew/lib", "/usr/local/lib"):
            if lib_path not in existing:
                existing = f"{lib_path}:{existing}" if existing else lib_path
        os.environ["DYLD_LIBRARY_PATH"] = existing
        from weasyprint import HTML
        return HTML
    except OSError as exc:
        raise PDFBuildError(
            "WeasyPrint could not load required system libraries (libpango, libcairo). "
            "On macOS install them with: brew install pango cairo "
            f"Original error: {exc}"
        ) from exc
    except ImportError as exc:
        raise PDFBuildError(
            "WeasyPrint is not installed. Run: pip install weasyprint>=62.0"
        ) from exc


def _require_jinja2():
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        return Environment, FileSystemLoader, select_autoescape
    except ImportError as exc:
        raise PDFBuildError(
            "Jinja2 is not installed. Run: pip install jinja2>=3.1.0"
        ) from exc


def _encode_asset(path: Path) -> str:
    if not path.exists():
        logger.warning("Asset not found: %s — logo will be omitted", path)
        return ""
    with open(path, "rb") as fh:
        raw = fh.read()
    b64 = base64.b64encode(raw).decode("ascii")
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{b64}"


def _process_photo(source: Any, max_width: int = 960) -> str | None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise PDFBuildError(
            "Pillow is not installed. Run: pip install Pillow>=10.0.0"
        ) from exc

    try:
        if hasattr(source, "seek"):
            source.seek(0)
            raw_bytes = source.read()
        elif isinstance(source, (bytes, bytearray)):
            raw_bytes = bytes(source)
        else:
            raw_bytes = bytes(source.read())

        img = Image.open(io.BytesIO(raw_bytes))

        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        if w > max_width:
            img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as exc:
        logger.warning("Could not process photo: %s — skipping", exc)
        return None


def _format_date(iso_date: str) -> str:
    try:
        from dateutil import parser as du_parser
        return du_parser.parse(iso_date).strftime("%B %d, %Y")
    except Exception:
        return iso_date


def _safe_str(value: Any, fallback: str = "Not provided for this assessment.") -> str:
    if value is None:
        return fallback
    s = str(value).strip()
    return s if s else fallback


def _safe_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    return []


def _build_template_context(
    content: dict,
    logo01_uri: str,
    logo02_uri: str,
    brand_blue: str = "#003DA5",
    brand_red: str = "#F5333F",
) -> dict:
    facility_name = _safe_str(content.get("facility_name"), "Facility Name")
    client_name = _safe_str(content.get("client_name"), "Client Name")
    apm_name = _safe_str(content.get("apm_name"), "APM Name")
    assessment_date = _format_date(
        str(content.get("assessment_date", date.today().isoformat()))
    )

    executive_summary = _safe_str(content.get("executive_summary"))
    exec_summary_callout = _safe_str(content.get("exec_summary_callout"), "")

    existing_conditions = _safe_list(content.get("existing_conditions"))
    failure_drivers = _safe_str(content.get("failure_drivers"), "")

    failure_analysis = _safe_str(content.get("failure_analysis"))
    failure_analysis_callout = _safe_str(content.get("failure_analysis_callout"), "")

    surface_preparation = _safe_str(content.get("surface_preparation"))

    standards = _safe_list(content.get("standards"))

    coating_system_raw = content.get("coating_system") or {}
    coating_system = {
        "name": _safe_str(coating_system_raw.get("name"), "See Assessment Narrative"),
        "description": _safe_str(coating_system_raw.get("description")),
        "coat_sequence": _safe_list(coating_system_raw.get("coat_sequence")),
        "pds_references": _safe_list(coating_system_raw.get("pds_references")),
    }
    coating_system_perf_notes = _safe_str(content.get("coating_system_perf_notes"), "")

    installation_notes = _safe_list(content.get("installation_notes"))
    if not installation_notes:
        installation_notes = ["Not provided for this assessment."]

    conclusion = _safe_str(content.get("conclusion"))
    conclusion_callout = _safe_str(content.get("conclusion_callout"), "")

    technical_references = _safe_list(content.get("technical_references"))

    # Build photo list with embedded data URIs
    photo_entries_raw = _safe_list(content.get("photos"))
    photos = []
    for i, entry in enumerate(photo_entries_raw):
        caption = _safe_str(entry.get("caption"), "No analysis available.")
        filename = entry.get("filename") or entry.get("file_path") or f"Photo {i + 1}"
        display_name = Path(str(filename)).name if filename else f"Photo {i + 1}"

        data_uri: str | None = None

        if entry.get("image_data_uri"):
            data_uri = str(entry["image_data_uri"])

        if data_uri is None and entry.get("file_path"):
            fp = str(entry["file_path"])
            if os.path.exists(fp):
                try:
                    with open(fp, "rb") as fh:
                        data_uri = _process_photo(fh)
                except Exception as exc:
                    logger.warning("Could not read photo file %s: %s", fp, exc)

        photos.append({
            "data_uri": data_uri,
            "caption": caption,
            "filename": display_name,
            "index": i + 1,
        })

    return {
        "logo01_uri": logo01_uri,
        "logo02_uri": logo02_uri,
        "brand_blue": brand_blue,
        "brand_red": brand_red,
        "facility_name": facility_name,
        "client_name": client_name,
        "apm_name": apm_name,
        "assessment_date": assessment_date,
        "executive_summary": executive_summary,
        "exec_summary_callout": exec_summary_callout,
        "existing_conditions": existing_conditions,
        "failure_drivers": failure_drivers,
        "photos": photos,
        "failure_analysis": failure_analysis,
        "failure_analysis_callout": failure_analysis_callout,
        "surface_preparation": surface_preparation,
        "coating_system": coating_system,
        "coating_system_perf_notes": coating_system_perf_notes,
        "standards": standards,
        "installation_notes": installation_notes,
        "conclusion": conclusion,
        "conclusion_callout": conclusion_callout,
        "technical_references": technical_references,
    }


def _register_nl2br(env) -> None:
    def nl2br(value: str) -> markupsafe.Markup:
        escaped = markupsafe.escape(value)
        return markupsafe.Markup(str(escaped).replace("\n", "<br>\n"))
    env.filters["nl2br"] = nl2br


_PREVIEW_CSS_OVERRIDE = """
<style>
  body { max-width: 900px; margin: 0 auto; padding: 32px 48px; background: #fff; }
  .cover-page { margin: 0 !important; padding: 40px !important;
                border-radius: 4px; min-height: auto !important; }
  #running-header { position: static; display: table; width: 100%;
                    margin-bottom: 20px; padding-bottom: 10px; }
</style>
"""


def render_preview_html(content: dict) -> str:
    """
    Render the report as browser-viewable HTML for the in-app preview pane.
    Reuses the same Jinja2 template as build_pdf() without running WeasyPrint.
    """
    if not _TEMPLATE_PATH.exists():
        raise PDFBuildError(
            f"PDF template not found at {_TEMPLATE_PATH}."
        )

    logo01_uri = content.get("logo01_uri_override") or _encode_asset(_LOGO_01_PATH)
    logo02_uri = content.get("logo02_uri_override") or _encode_asset(_LOGO_02_PATH)
    brand_blue = content.get("brand_blue", "#003DA5") or "#003DA5"
    brand_red = content.get("brand_red", "#F5333F") or "#F5333F"

    context = _build_template_context(content, logo01_uri, logo02_uri, brand_blue, brand_red)

    Environment, FileSystemLoader, select_autoescape = _require_jinja2()
    env = Environment(
        loader=FileSystemLoader(str(_ASSETS_DIR)),
        autoescape=select_autoescape(["html"]),
        keep_trailing_newline=True,
    )
    _register_nl2br(env)

    try:
        template = env.get_template("pdf_template.html")
        html_str = template.render(**context)
    except Exception as exc:
        raise PDFBuildError(f"Failed to render HTML template: {exc}") from exc

    return html_str.replace("</head>", _PREVIEW_CSS_OVERRIDE + "</head>", 1)


def build_pdf(content: dict) -> bytes:
    """
    Render a branded Sherwin-Williams Site Assessment PDF from the content dict.

    Parameters
    ----------
    content : dict
        Content dictionary returned by ai_generator.generate_site_assessment()
        (or its edited version from the Streamlit review section).

    Returns
    -------
    bytes
        Raw PDF bytes suitable for st.download_button() or writing to disk.

    Raises
    ------
    PDFBuildError
        If WeasyPrint fails, dependencies are missing, or the template is absent.
    """
    if not _TEMPLATE_PATH.exists():
        raise PDFBuildError(
            f"PDF template not found at {_TEMPLATE_PATH}. "
            "Ensure assets/pdf_template.html is present in the project directory."
        )

    logo01_uri = content.get("logo01_uri_override") or _encode_asset(_LOGO_01_PATH)
    logo02_uri = content.get("logo02_uri_override") or _encode_asset(_LOGO_02_PATH)

    brand_blue = content.get("brand_blue", "#003DA5") or "#003DA5"
    brand_red = content.get("brand_red", "#F5333F") or "#F5333F"

    context = _build_template_context(content, logo01_uri, logo02_uri, brand_blue, brand_red)

    Environment, FileSystemLoader, select_autoescape = _require_jinja2()

    env = Environment(
        loader=FileSystemLoader(str(_ASSETS_DIR)),
        autoescape=select_autoescape(["html"]),
        keep_trailing_newline=True,
    )
    _register_nl2br(env)

    try:
        template = env.get_template("pdf_template.html")
        html_str = template.render(**context)
    except Exception as exc:
        raise PDFBuildError(f"Failed to render HTML template: {exc}") from exc

    HTML = _require_weasyprint()

    try:
        pdf_bytes = HTML(
            string=html_str,
            base_url=str(_ASSETS_DIR),
        ).write_pdf()
    except Exception as exc:
        raise PDFBuildError(f"WeasyPrint failed to render the PDF: {exc}") from exc

    if not pdf_bytes:
        raise PDFBuildError("WeasyPrint produced an empty PDF output.")

    return pdf_bytes
