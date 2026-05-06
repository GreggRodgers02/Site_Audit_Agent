# PRD-03: Product Catalog & PDS Hyperlink Automation
**Site Audit Agent — Sherwin-Williams PCG Asset Protection**

---

## Document Information

| Field | Value |
|---|---|
| PRD ID | PRD-03 |
| Feature Name | Product Catalog & PDS Hyperlink Automation |
| Version | 1.0 |
| Date | 2026-05-05 |
| Author | PM Agent (Claude Code) |
| Status | Draft — Ready for Dev Review |
| Dependencies | PRD-01 (AI report generation), PRD-02 (PDF assembly via WeasyPrint) |

---

## 1. Overview

PRD-03 introduces a persistent product catalog and automated PDS (Product Data Sheet) hyperlink embedding. Today, APMs manually embed hyperlinks to Product Data Sheets in Adobe Acrobat after PDF export. This PRD eliminates that manual step by maintaining a catalog of SW protective/marine coating products and auto-embedding PDS links in the generated PDF.

---

## 2. Problem Statement

After a site audit report is generated and exported as a PDF, APMs open the document in Adobe Acrobat and manually locate each product name, then embed the correct PDS URL from sherwin-williams.com. This process:

- Requires the APM to know or look up the correct PDS URL for each product
- Is repeated for every report, even when the same products appear across multiple audits
- Introduces risk of incorrect or outdated URLs
- Adds 5–15 minutes of manual post-processing per report

**Desired State:** Product names in the coating system section are automatically identified, matched against a curated catalog, and rendered as clickable hyperlinks to the correct public PDS URL.

---

## 3. Goals & Objectives

### Primary Goal
Eliminate manual PDS hyperlinking in Adobe Acrobat by automating product recognition and link embedding during PDF generation.

### Secondary Goals
- Maintain a curated, version-controlled product catalog updatable without code changes
- Graceful fallback when a product is not found in the catalog
- Allow APMs to supply manual PDS URLs for unlisted or custom products

### Non-Goals
- UI for managing/editing the product catalog
- Fetching or caching live PDS PDFs from sherwin-williams.com
- Validating PDS URL liveness at generation time
- Product pricing, availability, or VOC compliance data
- Changes to PRD-01 AI prompts

---

## 4. Target Users

### Primary: Asset Protection Manager (APM)
Generates multiple reports per week. Pain point: repetitive Acrobat post-processing. Goal: complete, hyperlinked report in a single workflow.

### Secondary: Report Reviewer (Client or Internal)
Clicks PDS links to verify product specifications without searching sherwin-williams.com manually.

---

## 5. Proposed Solution

A lightweight, file-based product catalog (`data/products.json`) stores structured data for common SW Protective & Marine coating products. A Python module (`src/product_catalog.py`) provides catalog loading, fuzzy product name matching, and URL resolution. The existing PDF builder (`src/pdf_builder.py`) is extended to call the product catalog module and render matched product names as HTML anchor tags before WeasyPrint converts the document to PDF.

### Key Capabilities

1. **Catalog storage** — JSON file with 15+ seed products: name, product number, PDS URL, description, category, surface types
2. **Product matching** — fuzzy substring matching against APM free-text input, case-insensitive, tolerant of partial names
3. **URL resolution** — canonical PDS URL for matched products; parameterized SW search URL fallback
4. **Manual override** — APMs paste PDS URL in Streamlit UI for unmatched products
5. **PDF integration** — matched product names wrapped in `<a href="...">` tags → clickable hyperlinks in final PDF

---

## 6. Functional Requirements

### FR-01: Product Catalog File

Stored at `data/products.json`. Each entry must contain:

| Field | Type | Required | Description |
|---|---|---|---|
| `product_name` | string | Yes | Full canonical product name |
| `product_number` | string | Yes | SW product number |
| `pds_url` | string | Yes | Full public URL on sherwin-williams.com |
| `description` | string | Yes | One-sentence description |
| `category` | string | Yes | `primer` / `intermediate` / `topcoat` / `sealer` / `specialty` |
| `surface_types` | array | Yes | e.g., `["steel", "concrete", "galvanized"]` |
| `aliases` | array | No | Common alternate names/abbreviations |

Minimum 15 seed products at initial release. JSON must be human-readable and hand-editable.

### FR-02: Catalog Loading (`product_catalog.py`)

- `load_catalog()` reads `data/products.json` and returns a list of product dicts
- Cached in memory after first load — no repeated disk I/O per report
- Missing or malformed JSON: log clear error, return empty list without raising

### FR-03: Product Matching

- `match_products(text: str, catalog: list) -> list`
- Case-insensitive substring matching on `product_name` and `aliases`
- Longest (most specific) match wins when names overlap
- Returns: `product_name`, `product_number`, `pds_url`, `category`, `matched_on`, `match_confidence` (`exact` / `alias` / `partial`)
- Returns empty list on empty or null input — never raises

### FR-04: Fallback URL Resolution

- `resolve_pds_url(product_name: str) -> str`
- Returns catalog PDS URL if match exists
- Fallback: `https://www.sherwin-williams.com/en-us/search#q={encoded_product_name}&t=coveoSearch`
- Product name URL-encoded (no unencoded spaces)

### FR-05: Manual PDS URL Override (Streamlit UI)

After AI generation, before PDF export, display "Coating System Products" panel:
- List all identified products with resolved PDS URLs
- Warning indicator + optional text input for unmatched products
- Manual URLs override fallback for that product in PDF output
- Manual URLs are session-only (not persisted to catalog)
- Summary: "X of Y products matched in catalog. Z require manual URL or will use search fallback."

### FR-06: PDF Hyperlink Embedding

- `pdf_builder.py` calls `match_products()` before HTML template rendering
- Product names in coating system section replaced with `<a href="{pds_url}" style="color: #003DA5; text-decoration: underline;">{product_name}</a>`
- Priority: manual override URL > catalog URL > fallback URL
- Only first occurrence of each product name is hyperlinked
- Hyperlinking scoped exclusively to the coating system section

### FR-07: Catalog Seed Data (15 minimum)

| Product Name | Category | Primary Use |
|---|---|---|
| Macropoxy 646 | intermediate | Steel, immersion service |
| Macropoxy 920 | intermediate | Steel, fast-cure |
| Zinc Clad IV | primer | Galvanized, steel (zinc-rich) |
| Zinc Clad 11 HS | primer | Steel (inorganic zinc) |
| Tile-Clad HS | topcoat | Steel, concrete |
| Sher-Cryl HPA | topcoat | Concrete, masonry |
| Corothane I GalvaPac | primer | Galvanized steel |
| Corothane I Mastic | intermediate | Steel, pitted surfaces |
| Hi-Mil SG-100 | specialty | Steel, thick-film immersion |
| Dura-Plate 235 | intermediate | Steel, concrete |
| Dura-Plate UHS | intermediate | Steel, high-build |
| Recoatable Epoxy Primer | primer | Steel, concrete |
| Epo-Plex 880 | specialty | Concrete immersion |
| Kem Aqua Plus | topcoat | Interior steel, concrete |
| Firetex M90/02 | specialty | Structural steel (intumescent) |
| Sher-Bar Piling Jacket | specialty | Marine piling |
| Marathon | topcoat | Exterior steel, industrial |

---

## 7. Technical Specifications

### 7.1 File Structure

```
Site_Audit_Agent/
├── data/
│   └── products.json          # Catalog seed file
├── src/
│   ├── product_catalog.py     # Catalog module (new)
│   └── pdf_builder.py         # Extended (PRD-02)
```

### 7.2 `data/products.json` Schema

```json
[
  {
    "product_name": "Macropoxy 646",
    "product_number": "B58W600",
    "pds_url": "https://www.sherwin-williams.com/content/dam/sherwin-williams/documents/product-data-sheets/protective/pds-macropoxy-646-b58w600.pdf",
    "description": "Fast-cure epoxy intermediate/topcoat for steel and concrete in atmospheric and immersion service.",
    "category": "intermediate",
    "surface_types": ["steel", "concrete", "galvanized"],
    "aliases": ["MP646", "B58W600"]
  }
]
```

### 7.3 `src/product_catalog.py` Public Interface

```python
def load_catalog(catalog_path: str = "data/products.json") -> list[dict]:
    """Loads and caches the product catalog from disk."""

def match_products(text: str, catalog: list[dict] | None = None) -> list[dict]:
    """
    Parses free-text coating system input and returns matched product entries.
    Each result: {product_name, product_number, pds_url, category, matched_on, match_confidence}
    """

def resolve_pds_url(product_name: str, catalog: list[dict] | None = None) -> str:
    """Returns PDS URL for product, or parameterized SW search URL if not found."""
```

### 7.4 Matching Algorithm

1. Normalize input text and all `product_name` / `aliases` to lowercase
2. Build sorted list of (token, catalog_entry, confidence) by token length descending
3. Scan input with `re.search` for each token; track matched spans (longest wins)
4. Return match results in order of appearance in input text
5. No external fuzzy-matching library required — Python stdlib `re` module sufficient

### 7.5 `pdf_builder.py` Integration Contract

- Import `product_catalog` and call `match_products()` on coating system section text
- Accept optional `manual_urls: dict[str, str]` parameter from Streamlit session state
- URL priority: `manual_urls[product_name]` > `catalog pds_url` > fallback
- HTML replacement operates on rendered coating system HTML string before WeasyPrint
- Replacement function must be idempotent

### 7.6 Streamlit Session State Keys

| Key | Type | Description |
|---|---|---|
| `st.session_state.matched_products` | list[dict] | Result of `match_products()` for current report |
| `st.session_state.manual_pds_urls` | dict[str, str] | APM-supplied manual URLs, keyed by product name |

### 7.7 Dependencies

No new Python packages. Uses stdlib only:
- `json`, `re`, `urllib.parse`, `logging`

### 7.8 Performance Requirements

- `load_catalog()` cold load: under 100ms on VPS
- `match_products()` on 2,000-char input against 50-entry catalog: under 50ms

---

## 8. User Stories

**US-001** — Catalog JSON with seed data: `data/products.json` exists, is valid JSON, contains 15+ products with all required fields.

**US-002** — Catalog loads without repeated disk reads: second call returns cached list; missing file returns empty list with log error.

**US-003** — Exact product name match returns catalog entry with `match_confidence = "exact"`.

**US-004** — Case-insensitive matching resolves "tile-clad hs", "TILE-CLAD HS", "Tile-Clad Hs" correctly.

**US-005** — Alias matching resolves "MP646" to "Macropoxy 646" with `match_confidence = "alias"`.

**US-006** — Longest match wins: "Zinc Clad IV" in input does not also match a "Zinc Clad" substring.

**US-007** — Empty/null input returns empty list, no exception.

**US-008** — Matched product returns canonical PDS URL from catalog.

**US-009** — Unmatched product returns parameterized SW search URL with URL-encoded name.

**US-010** — APM sees "Coating System Products" panel after generation with product list and PDS URL preview.

**US-011** — Unmatched products shown with warning indicator and manual URL input field.

**US-012** — APM-supplied manual URL used in PDF instead of fallback; warning cleared on input.

**US-013** — Product names in PDF coating system section are clickable hyperlinks in `#003865` (SW Navy), underlined.

**US-014** — Only first occurrence of each product name is hyperlinked (no redundant links).

**US-015** — Product names outside the coating system section are NOT hyperlinked.

---

## 9. Acceptance Criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-01 | `products.json` is valid JSON with 15+ products, all required fields | Automated schema validation |
| AC-02 | `load_catalog()` returns non-empty list | Unit test |
| AC-03 | `load_catalog()` returns empty list on missing file | Unit test |
| AC-04 | All 15 seed products matchable by exact name | Parameterized unit test |
| AC-05 | Case-insensitive matching works | Unit test |
| AC-06 | Empty/null input returns empty list | Unit test |
| AC-07 | `resolve_pds_url()` returns catalog URL for known product | Unit test |
| AC-08 | `resolve_pds_url()` returns SW search URL with encoded name for unknown product | Unit test |
| AC-09 | PDF with 2+ catalog products has clickable hyperlinks in coating section | Manual in Acrobat and Preview |
| AC-10 | Hyperlink color is visually consistent with `#003865` | Visual inspection |
| AC-11 | APM manual URL appears in PDF for unmatched product | End-to-end test |
| AC-12 | Products outside coating section are not hyperlinked | Manual inspection |
| AC-13 | "Coating System Products" panel appears after generation | Manual UI walkthrough |
| AC-14 | Unmatched products show warning + manual URL field | Manual UI walkthrough |
| AC-15 | No new Python packages added to `requirements.txt` | Diff against PRD-02 baseline |

---

## 10. Out of Scope (Future Phases)

| Item | Rationale |
|---|---|
| Catalog management UI | JSON is hand-editable for the near term |
| SQLite migration for catalog | Appropriate when catalog exceeds ~100 entries |
| Live PDS URL validation | Adds latency; URLs are curated and stable |
| SW website scraping for auto-updates | Legal/ToS risk |
| Edit-distance / phonetic fuzzy matching | Substring matching sufficient for controlled APM input |
| Product recommendations by surface type | Separate advisory feature |
| Saving APM manual URLs back to catalog | Requires catalog management UI |

---

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| PDS URLs change on SW site redesign | Medium | Medium | Single `products.json` file; URL audit without code changes; note to verify quarterly |
| Substring false positives (e.g., "Zinc" matching multiple products) | Medium | Low | Longest-match-first algorithm; APM can verify in Streamlit panel |
| APM free-text too abbreviated for catalog match | Medium | Low | Fallback URL ensures no broken links; aliases extensible in JSON |
| WeasyPrint strips anchor `href` attributes | Low | High | Validate WeasyPrint anchor handling in standalone spike before integration |

---

## 12. Open Questions

| ID | Question |
|---|---|
| OQ-01 | Are there additional SW Protective & Marine products APMs frequently use not on the seed list? |
| OQ-02 | Should "Coating System Products" panel be collapsible to avoid UI clutter? |
| OQ-03 | Is there a canonical SW PDS URL pattern buildable from product numbers programmatically? |
| OQ-04 | Should unmatched products block PDF generation or proceed with fallback + warning? (Current spec: non-blocking) |

---

*End of PRD-03 — Product Catalog & PDS Hyperlink Automation*
*Version 1.0 | 2026-05-05 | Site Audit Agent — Sherwin-Williams PCG Asset Protection*
