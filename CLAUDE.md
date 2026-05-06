# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
# Activate the project virtualenv first
source .venv/bin/activate

# Start the Streamlit app
streamlit run app.py
```

The app runs on `http://localhost:8501` by default.

## Environment variables

Copy `.env` and fill in values before running. Required keys:

```
OPENAI_API_KEY=sk-...
OPENAI_PRIMARY_MODEL=gpt-4o          # or any chat-completions-compatible model
OPENAI_FALLBACK_MODEL=gpt-4o-mini    # used automatically if primary is unavailable
```

The web-search step (`_web_research_coating_system`) calls `client.responses.create()` with `model="gpt-4o-mini"` unconditionally — it requires the OpenAI Responses API (SDK ≥1.30). It fails silently if the key or model doesn't support it.

## Architecture

### Request flow

```
Intake form (app.py)
  └─ generate_site_assessment()        ← src/ai_generator.py
       ├─ _web_research_coating_system()   OpenAI Responses API + web_search_preview
       ├─ _analyze_photo()  ×N             Vision API, one call per uploaded photo
       └─ _generate_narrative()            Single large chat call → 8-section report
            └─ parsers (_parse_*)          Regex extraction → structured fields
  └─ st.session_state stores result
  └─ APM edits each section in-place
  └─ build_pdf()                       ← src/pdf_builder.py
       ├─ _build_template_context()        Merges edited fields → Jinja2 vars
       ├─ Jinja2 renders pdf_template.html ← assets/pdf_template.html
       └─ WeasyPrint → bytes → download
  └─ save_report()                     ← src/document_library.py (SQLite)
```

### Key design decisions

**Session state persistence.** After generation `_init_edit_state(result)` writes every editable field into `st.session_state` under `ed_*` keys. All subsequent re-runs (PDF button, sidebar interactions) read from those keys — never from the form. `_build_pdf_content()` assembles the final dict from session state immediately before PDF rendering.

**Pipe-separated text encoding.** List-of-dicts fields (`existing_conditions`, `coat_sequence`) are serialised to human-editable plain text using ` | ` as a field separator and one item per line. `_text_to_conditions()` and `_text_to_coat_sequence()` parse them back before PDF generation.

**Prompt structured markers.** The narrative prompt uses `CONDITION:`, `BULLET:`, `COAT:`, `CALLOUT:`, `REF:`, etc. as line-level markers. The `_parse_*` family of functions in `ai_generator.py` use `re.search`/`re.finditer` against these markers to extract structured data from the free-text LLM output. If a section is missing or the markers aren't present, each parser has a fallback (bullet stripping, paragraph splitting).

**PDF template layout.** `assets/pdf_template.html` is a Jinja2+WeasyPrint document. WeasyPrint does not support flexbox or CSS grid — all multi-column layouts use `display: table` / `display: table-cell`. Photos render in a 2-column grid using a `{% for row_i in range(...) %}` loop that emits a `<table>` per row pair. Running header/footer use WeasyPrint's named `@page` areas and `position: running(...)`.

**No local product catalog.** Product information comes entirely from the AI (training knowledge + optional live web search). `src/product_catalog.py` remains in the repo but is no longer imported by `app.py` or `pdf_builder.py`.

### Module responsibilities

| File | Responsibility |
|---|---|
| `app.py` | Streamlit UI: form, session state, edit section, PDF trigger, sidebar library |
| `src/ai_generator.py` | OpenAI calls: web research, photo vision, narrative generation, all section parsers |
| `src/pdf_builder.py` | Jinja2 render → WeasyPrint → PDF bytes; template context assembly |
| `assets/pdf_template.html` | Branded HTML template; all CSS lives inline; 9-section SW report layout |
| `src/document_library.py` | SQLite CRUD for report metadata; PDF saved to `reports/`; DB at `data/reports.db` |
| `src/product_catalog.py` | Legacy fuzzy catalog matcher — not used in current flow |

### Generated report sections

The AI narrative prompt requests 8 sections using structured line markers; the PDF template renders 9 sections (section 3 — Photo Log — is injected by the PDF builder, not the LLM):

1. Introduction / Executive Summary  
2. Existing Conditions and Observed Distress  
3. Photo Log and Image-Based Observations *(photos from upload, not LLM)*  
4. Observed Failure Analysis  
5. Surface Preparation Requirements (AMPP and ICRI Basis)  
6. Proposed Recommended Coating System  
7. Installation Notes and Precautions  
8. Conclusion  
9. Technical Reference Basis  

### Dependencies

WeasyPrint requires native system libraries. On macOS:

```bash
brew install pango cairo
```

`pdf_builder.py` prepends `/opt/homebrew/lib` to `DYLD_LIBRARY_PATH` automatically at import time.
