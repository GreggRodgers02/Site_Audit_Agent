# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
source .venv/bin/activate
streamlit run app.py
```

The app runs on `http://localhost:8501` by default. Leave `APP_PASSWORD_HASH` unset in `.env` to skip the login gate during local development.

## Environment variables

`.env` is loaded by `python-dotenv` at startup. For Streamlit Community Cloud, put these in the dashboard Secrets panel instead (as TOML). Reference: `.streamlit/secrets.toml.example`.

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Required. |
| `OPENAI_NARRATIVE_MODEL` | Main document generation. Default `gpt-5.4`. |
| `OPENAI_PRIMARY_MODEL` | Vision + change requests. Default `gpt-4o`. |
| `OPENAI_FALLBACK_MODEL` | Auto-fallback if primary unavailable. Default `gpt-4o-mini`. |
| `APP_PASSWORD_HASH` | SHA-256 hex of the login password. Omit to run without auth. |

Generate `APP_PASSWORD_HASH`:
```bash
python -c "import hashlib; print(hashlib.sha256(b'yourpassword').hexdigest())"
```

## Architecture

### AI generation pipeline (`src/ai_generator.py`)

Steps run in this order inside `generate_site_assessment()`:

1. **Photo analysis** (`_analyze_photo()` × N) — `gpt-4o` vision, `detail: "high"`, one call per photo. Runs first so findings are available for step 2.
2. **Web research** (`_web_research_coating_system()`) — `gpt-4o-mini` + `web_search_preview` via OpenAI Responses API. Receives both the APM-specified system name and a summary of observed conditions from step 1 so searches target the actual substrate/failure modes. Runs even when no system is pre-specified.
3. **Narrative generation** (`_generate_narrative()`) — single large call to `OPENAI_NARRATIVE_MODEL`. Prompt uses line-level markers (`CONDITION:`, `BULLET:`, `COAT:`, `CALLOUT:`, `REF:`, etc.) that the `_parse_*` family of functions extract via regex. Each parser has a fallback for missing markers.
4. **PDS URL backfill** — after parsing, any coat in the sequence with an empty `pds_url` gets a targeted `_lookup_pds_url()` web search call. The narrative model often outputs `UNKNOWN` for PDS URLs; this step reliably fills them in.

`_call_with_fallback()` wraps photo analysis and change-request calls: on model-availability errors it retries with `OPENAI_FALLBACK_MODEL`; rate-limit and auth errors surface immediately.

### Session state flow (`app.py`)

After generation, `_init_edit_state(result)` writes every editable field into `st.session_state` under `ed_*` keys. All subsequent page re-runs (preview, PDF export, sidebar interactions) read exclusively from `ed_*` keys — never from the original generation result. `_build_pdf_content()` assembles the final dict from session state immediately before rendering.

**Serialization:** `existing_conditions` (list of `{condition, note}`) and `coat_sequence` (list of `{coat, product, reason, pds_url}`) are round-tripped through human-editable plain text using ` | ` as a field separator, one item per line. `_text_to_conditions()` and `_text_to_coat_sequence()` parse them back. The coat sequence text area is the canonical place APMs can manually add or correct PDS URLs.

**Change history:** each AI change request applied via `apply_change_request()` is appended to `st.session_state["change_history"]` and shown in a collapsible section.

### PDF rendering (`src/pdf_builder.py`)

`build_pdf()` calls `_require_weasyprint()` which prepends both `/opt/homebrew/lib` (Apple Silicon) and `/usr/local/lib` (Intel Mac) to `DYLD_LIBRARY_PATH` before importing WeasyPrint.

`render_preview_html()` reuses the same Jinja2 template but skips WeasyPrint — it injects `_PREVIEW_CSS_OVERRIDE` to make the document scroll-friendly in the browser.

The `nl2br` Jinja2 filter is registered manually in both render paths; it is not built-in.

**Template constraints:** `assets/pdf_template.html` targets WeasyPrint, which does not support flexbox or CSS grid. All multi-column layouts use `display: table` / `display: table-cell`. The running page header uses WeasyPrint-specific `position: running(running-header)` and `@top-left { content: element(...) }` — do not replace with standard CSS positioning.

### Auth gate (`app.py`)

Checked at module load time before any UI renders. `_get_stored_hash()` reads `APP_PASSWORD_HASH` from `st.secrets` first, then `os.environ`. If set, unauthenticated users see only the login form. The plain-text password is hashed with `hashlib.sha256` and compared — users type their plain password, not the hash.

### Sidebar branding

`brand_logo1` and `brand_logo2` session state keys hold raw `UploadedFile` objects. `_build_pdf_content()` calls `_encode_logo_upload()` at render time (not at upload time) to produce base64 data URIs. Brand colors (`brand_blue`, `brand_red`) are passed as Jinja2 variables and replace all hardcoded hex values in the template.

## Deployment

### Streamlit Community Cloud

`packages.txt` in the repo root lists apt packages that Streamlit Cloud installs before starting the app. Required for WeasyPrint on Linux (Debian Trixie):

```
libpango-1.0-0
libpangocairo-1.0-0
libcairo2
libgdk-pixbuf-2.0-0
shared-mime-info
```

Note: use `libgdk-pixbuf-2.0-0` (not `libgdk-pixbuf2.0-0`) — the latter was renamed in Debian 13.

Secrets go in the Streamlit Cloud dashboard → App settings → Secrets (TOML format, same keys as `.env`).

### VPS (Ubuntu 22.04)

See `deploy/README.md` for the full guide. Key files:

- `deploy/setup.sh` — one-shot installer; set `REPO_URL` before running
- `deploy/site-audit-agent.service` — systemd unit; set `User=` to the deploy user
- `deploy/nginx.conf` — reverse proxy to Streamlit on port 8501; includes WebSocket upgrade headers required for Streamlit

Update command sequence:
```bash
cd /srv/site-audit-agent && git pull
/srv/site-audit-agent/venv/bin/pip install -r requirements.txt
sudo systemctl restart site-audit-agent
```

## Dependencies

WeasyPrint requires native system libraries:

```bash
# macOS (Apple Silicon)
brew install pango cairo

# macOS (Intel) — Homebrew installs to /usr/local, pdf_builder.py handles both paths automatically
brew install pango cairo
```

On Linux (VPS), install via apt before `pip install weasyprint` (see `deploy/README.md` § WeasyPrint errors).

`src/product_catalog.py` is a legacy fuzzy catalog matcher that is no longer imported anywhere. Do not re-import it.
