# PRD-01: Project Skeleton + AI Core
**Site Audit Agent — Sherwin-Williams PCG Asset Protection**

---

**Document Version:** 1.0
**Date:** 2026-05-05
**Author:** PM Agent (claude-sonnet-4-6)
**Project:** Site Audit Agent
**PRD ID:** PRD-01
**Status:** Draft — Awaiting Stakeholder Review
**Stakeholders:** Asset Protection Managers (APMs), PCG Field Operations, Engineering Lead

---

## Table of Contents

1. [Overview](#overview)
2. [Problem Statement](#problem-statement)
3. [Goals & Objectives](#goals--objectives)
4. [Target Users](#target-users)
5. [Proposed Solution](#proposed-solution)
6. [Functional Requirements](#functional-requirements)
7. [Technical Specifications](#technical-specifications)
8. [User Stories](#user-stories)
9. [Acceptance Criteria](#acceptance-criteria)
10. [Out of Scope](#out-of-scope)
11. [Risks & Mitigations](#risks--mitigations)
12. [Success Criteria](#success-criteria)

---

## 1. Overview

PRD-01 establishes the foundational skeleton of the Site Audit Agent application and wires up the AI core that powers report generation. This is the first of multiple planned PRDs and delivers the minimum viable backend + frontend scaffolding necessary for all subsequent features (PDF generation, SQLite storage, branding, deployment) to build upon.

Upon completion of PRD-01, an APM will be able to open the application, fill out a structured intake form, upload site photos, paste a coating system specification, and receive a fully generated site assessment narrative — produced by OpenAI's vision and text models — directly in the browser. No PDF export, no persistent storage, and no branded formatting are included in this phase; those are addressed in future PRDs.

**Primary Outcome:** A working, locally-runnable Streamlit application that accepts APM inputs and returns a structured AI-generated site assessment text block.

---

## 2. Problem Statement

### Current State

Sherwin-Williams PCG Asset Protection Managers conduct on-site facility audits and are responsible for producing written assessment reports that document observed coating failures, recommend surface preparation standards, and specify the appropriate coating system for remediation. Today, APMs manually author these reports by:

1. Reviewing site photographs individually
2. Drafting failure analysis narratives from memory and field notes
3. Cross-referencing product data sheets (PDS) and application guides manually
4. Ensuring AMPP and ICRI surface preparation standards are correctly cited
5. Formatting the final document for client presentation

APMs currently accomplish some of this using Microsoft Copilot with informal prompts, but the process is manual, inconsistent across team members, and still requires significant time to produce a presentable output.

**Estimated time per audit report: 1-2 hours.**

### Desired State

An APM completes a structured intake form in under 5 minutes, uploads their site photos, pastes the coating system specification, and receives a professionally structured assessment narrative — complete with failure analysis per photo, AMPP/ICRI standard references, and coating system write-up — generated automatically.

### Why This Matters

- At scale, this reclaims 1–2 hours per audit per APM, multiplied across the entire PCG field team.
- Inconsistent report quality creates liability exposure and undermines client confidence. Standardization reduces both.
- The existing Copilot workflow is informal, prompt-dependent, and not reproducible. A purpose-built tool enforces quality and consistency.

---

## 3. Goals & Objectives

### Primary Goal

Deliver a locally-runnable project skeleton with a functional Streamlit intake form and a working OpenAI API integration that generates a complete site assessment narrative from APM inputs and uploaded photos.

### Secondary Goals

- Establish a clean, extensible project structure that all future PRDs build upon without refactoring
- Encode the existing Copilot prompts into engineered system and user prompts that produce superior, reproducible outputs
- Implement model fallback logic (`gpt-5.5` → `gpt-5.4`) to ensure resilience against API availability issues
- Provide a `.env.example` and `.gitignore` that prevent credential leakage from day one

### Non-Goals (Explicit Exclusions for PRD-01)

- PDF generation or export (PRD-02)
- Branded cover page or visual formatting (PRD-02)
- SQLite storage or report history (PRD-04)
- User authentication or multi-user sessions (future PRD)
- Deployment to Hostinger VPS or Nginx configuration (PRD-05)
- Client-facing portal or shareable links (future PRD)
- Editing or regenerating individual sections of a report (future PRD)

---

## 4. Target Users

### Primary Persona: Asset Protection Manager (APM)

- **Role:** Field-based coatings specialist employed by Sherwin-Williams PCG
- **Technical comfort:** Moderate. Comfortable with web tools and Microsoft Office; not a developer
- **Context of use:** In the field or back at the office immediately post-audit, often time-pressured
- **Primary pain point:** Report writing consumes disproportionate time relative to the value it adds; the expertise is already in the APM's head — the tool should extract and structure it, not require the APM to author from scratch
- **Goal:** Produce a polished, accurate, client-ready assessment in a fraction of current time

### Secondary Persona: PCG Operations / Management

- **Role:** Reviews reports for quality, consistency, and client delivery
- **Primary concern:** Ensuring all reports meet professional and technical standards (AMPP, ICRI references, PDS citations)
- **Goal:** Trust that outputs are consistently high quality regardless of which APM produced them

---

## 5. Proposed Solution

### High-Level Description

A Python/Streamlit web application with a multi-step intake form. The APM fills in facility and client details, uploads photos taken during the site visit, and pastes the recommended coating system specification. On submission, the application sends the inputs to the OpenAI API — using vision capabilities for photo analysis and text generation for the narrative — and renders the completed assessment in the browser.

### Key Capabilities Delivered in PRD-01

**Intake Form (`app.py`)**
- Step 1: Facility name (text input) and client name (text input)
- Step 2: Photo uploads (multi-file image uploader, accepts JPG/PNG)
- Step 3: Recommended coating system specification (text area)
- Step 4: "Generate Report" button triggers the AI pipeline

**AI Generation Pipeline (`src/ai_generator.py`)**
- Per-photo vision analysis: Each uploaded image is sent to the model individually to extract observed coating failures, surface conditions, and relevant defects
- Consolidated narrative generation: All per-photo findings, facility metadata, and the coating system spec are assembled into a single prompt that generates the full assessment document
- Output sections: Introduction, Observed Failure Analysis (by photo), Recommended Coating System with PDS critical information, Surface Preparation standards (AMPP/ICRI references)
- Model routing: Primary model `gpt-5.5`, automatic fallback to `gpt-5.4` on API error

### Integration Points

- OpenAI API (external): Vision and chat completions endpoints
- `.env` file: API key injection via `python-dotenv`
- Streamlit session state: Holds form data and generated output within a single session (no persistence in PRD-01)

---

## 6. Functional Requirements

### FR-01: Project Scaffolding

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.1 | A `requirements.txt` must be present at project root listing all dependencies with pinned or minimum version constraints: `streamlit`, `openai`, `weasyprint`, `Pillow`, `python-dotenv` and any transitive dependencies required for local execution | Must Have |
| FR-01.2 | A `.env.example` file must be present at project root containing placeholder keys for all required environment variables, with comments describing each variable's purpose | Must Have |
| FR-01.3 | A `.gitignore` must be present at project root that excludes: `.env`, `__pycache__/`, `*.pyc`, `.DS_Store`, `venv/`, `.venv/`, and any generated output files (e.g., `*.pdf`, `output/`) | Must Have |
| FR-01.4 | The `src/` directory must exist and contain an `__init__.py` to make it a proper Python package | Must Have |

### FR-02: Streamlit Intake Form (`app.py`)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-02.1 | The application must display a page title and brief description that contextualizes the tool for the APM | Must Have |
| FR-02.2 | The form must include a text input field labeled "Facility Name" | Must Have |
| FR-02.3 | The form must include a text input field labeled "Client Name" | Must Have |
| FR-02.4 | The form must include a multi-file uploader that accepts `.jpg`, `.jpeg`, and `.png` files | Must Have |
| FR-02.5 | The form must include a text area labeled "Recommended Coating System" with placeholder text | Must Have |
| FR-02.6 | The form must include a "Generate Report" button that is disabled if required fields are missing | Must Have |
| FR-02.7 | While report generation is in progress, the UI must display a spinner or progress indicator | Must Have |
| FR-02.8 | On successful generation, the full report text must be rendered in the Streamlit UI | Must Have |
| FR-02.9 | On API error or generation failure, the UI must display a user-friendly error message | Must Have |

### FR-03: AI Generation Module (`src/ai_generator.py`)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-03.1 | The module must expose a primary public function `generate_site_assessment` accepting facility name, client name, photo file objects, and coating system spec | Must Have |
| FR-03.2 | Each uploaded image must be processed individually through the OpenAI vision API | Must Have |
| FR-03.3 | Per-photo vision prompts must identify: failure type, affected substrate, severity, and surface contamination | Must Have |
| FR-03.4 | The consolidated narrative prompt must incorporate all per-photo findings, facility metadata, coating system spec, and AMPP/ICRI standard references | Must Have |
| FR-03.5 | The system prompt must establish the model's role as a professional coatings assessment expert authoring a formal client report | Must Have |
| FR-03.6 | The generated report must contain: (1) Introduction/Executive Summary, (2) Observed Failure Analysis, (3) Recommended Coating System, (4) Surface Preparation Requirements, (5) Conclusion | Must Have |
| FR-03.7 | Primary model: `gpt-5.5`. Automatic fallback to `gpt-5.4` on unavailability error | Must Have |
| FR-03.8 | OpenAI API key must be loaded exclusively from environment variable `OPENAI_API_KEY` | Must Have |
| FR-03.9 | Images must be base64-encoded before transmission to the OpenAI vision API | Must Have |
| FR-03.10 | The module must raise a descriptive `AIGenerationError` on unrecoverable failures | Must Have |

---

## 7. Technical Specifications

### 7.1 Technology Stack

| Component | Technology | Version Constraint |
|-----------|------------|-------------------|
| Language | Python | >= 3.10 |
| UI Framework | Streamlit | >= 1.32.0 |
| AI Provider | OpenAI Python SDK | >= 1.30.0 |
| PDF Library (future use) | WeasyPrint | >= 62.0 |
| Image Processing | Pillow | >= 10.0.0 |
| Env Management | python-dotenv | >= 1.0.0 |

### 7.2 File Structure

```
Site_Audit_Agent/
├── app.py                  # Streamlit entry point, intake form, UI orchestration
├── requirements.txt        # All Python dependencies
├── .env.example            # Placeholder environment variable template
├── .gitignore              # Standard Python + project-specific ignores
└── src/
    ├── __init__.py         # Package init
    └── ai_generator.py     # OpenAI API integration, prompt engineering, fallback logic
```

### 7.3 Environment Variables

```
# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Model Configuration (optional overrides)
OPENAI_PRIMARY_MODEL=gpt-5.5
OPENAI_FALLBACK_MODEL=gpt-5.4
```

### 7.4 AI Prompt Design

**System Prompt:** Establish the assistant as a senior coatings assessment specialist with expertise in industrial protective coatings, AMPP standards (formerly SSPC/NACE), ICRI concrete surface preparation standards, and Sherwin-Williams PCG product lines. Formal and professional tone.

**Per-Photo Vision Prompt:** Identify visible coating failure modes, substrate type and condition, estimated severity (light/moderate/severe), and surface contamination indicators. Structured output (bullet points).

**Consolidated Report Prompt:** Must pass facility name, client name, per-photo findings, and coating system spec. Must explicitly instruct the model to:
- Reference applicable AMPP surface preparation standards (e.g., SSPC-SP 6, SP 10, SP 13)
- Reference applicable ICRI guidelines (e.g., ICRI 310.2) where concrete substrates are present
- Extract and cite critical application parameters from the pasted coating system spec

### 7.5 Error Handling Strategy

| Error Condition | Handling Behavior |
|----------------|-------------------|
| `OPENAI_API_KEY` not set | Raise `AIGenerationError` before any API call |
| `gpt-5.5` model unavailable | Automatically retry with `gpt-5.4`; log fallback to console |
| Both models unavailable | Raise `AIGenerationError` |
| API rate limit (429) | Raise `AIGenerationError` advising retry |
| Network timeout | Raise `AIGenerationError` with timeout context |

---

## 8. User Stories

**US-001 — Project scaffolding**
As a developer onboarding to the project, I want a complete `requirements.txt`, `.env.example`, and `.gitignore`, so that I can set up my local environment in a single `pip install` step.

**US-002 — `src/` package initialization**
As a developer building subsequent modules, I want the `src/` directory initialized as a proper Python package, so that imports resolve correctly.

**US-003 — Intake form: facility and client fields**
As an APM, I want clearly labeled text fields for facility name and client name, so that the report is correctly addressed.

**US-004 — Intake form: multi-photo uploader**
As an APM, I want to upload multiple site photos in a single interaction, so that all photographic evidence is available for analysis.

**US-005 — Intake form: coating system text area**
As an APM, I want to paste the full coating system specification into a text area, so that the AI can incorporate product-specific details directly.

**US-006 — Generation trigger and in-progress state**
As an APM, I want clear feedback while the report is being generated, so that I know the system is working.

**US-007 — Per-photo vision analysis**
As an APM, I want each uploaded photo analyzed individually, so that the report contains photo-by-photo failure analysis.

**US-008 — Consolidated site assessment narrative**
As an APM, I want a complete professionally written site assessment narrative, so that I have a client-ready document structure.

**US-009 — Model fallback from `gpt-5.5` to `gpt-5.4`**
As a developer, I want the AI module to automatically fall back to `gpt-5.4` if `gpt-5.5` is unavailable, so that APMs are not blocked.

**US-010 — API key security**
As a developer, I want the API key loaded exclusively from environment variables, so that credentials are never committed to version control.

**US-011 — Graceful error handling**
As an APM, I want a clear actionable error message if report generation fails, so that I know whether to retry or contact support.

---

## 9. Acceptance Criteria (Feature-Level Gate)

### Completeness Gate
- [ ] All five files exist: `app.py`, `requirements.txt`, `.env.example`, `.gitignore`, `src/ai_generator.py`
- [ ] `src/__init__.py` exists
- [ ] `pip install -r requirements.txt` completes without errors in a clean Python 3.10+ virtual environment

### Functional Gate
- [ ] Application starts with `streamlit run app.py` without errors when `.env` is populated
- [ ] All four intake form fields render correctly and accept input
- [ ] Form validation prevents submission when required fields are absent
- [ ] A report generation with valid inputs produces output containing all five required sections
- [ ] Generated output contains at least one AMPP standard reference
- [ ] Generated output correctly reflects the facility name and client name provided

### Security Gate
- [ ] No API key or sensitive credential appears in any committed file
- [ ] `.env` is listed in `.gitignore`
- [ ] Missing `OPENAI_API_KEY` causes a clean `AIGenerationError` in the UI

### Resilience Gate
- [ ] Invalid primary model triggers automatic fallback and a console log entry
- [ ] All error paths in `ai_generator.py` result in `AIGenerationError`
- [ ] All `AIGenerationError` instances display a user-friendly message in the UI

---

## 10. Out of Scope (PRD-01)

| Capability | Planned PRD |
|-----------|-------------|
| PDF generation and export | PRD-02 |
| SW logo and branding | PRD-02 |
| SQLite database and report persistence | PRD-04 |
| Image resizing for PDF layout | PRD-02 |
| User authentication | Future PRD |
| VPS deployment and Nginx | PRD-05 |
| PDS hyperlinks | PRD-03 |

---

## 11. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R-01 | `gpt-5.5` model ID incorrect or unavailable | Medium | High | Fallback to `gpt-5.4`; model names configurable via env vars |
| R-02 | Large image sets cause high latency/cost | Medium | Medium | Accept latency in PRD-01; async processing in future PRD |
| R-03 | Vision model hallucinates failure types | Medium | High | Prompt instructs model to qualify uncertainty; APM reviews before delivery |
| R-04 | Coating system spec formats vary widely | High | Medium | Prompt robust to unstructured input; model notes missing parameters |
| R-05 | AMPP citations may be inaccurate | Low-Medium | High | Prompt specifies common standards as defaults; APMs verify before delivery |

---

## 12. Success Criteria

| Metric | Target |
|--------|--------|
| Report generation time (up to 5 photos) | < 90 seconds |
| APM time per report (end-to-end) | < 15 minutes |
| Required sections in output | 5/5 in 100% of reports |
| AMPP standard reference inclusion | >= 95% of reports |

**PRD-01 is complete when:**
1. All files in the specified structure exist and are committed
2. Application runs end-to-end locally with a valid `.env`
3. Test report with sample inputs produces output meeting the five-section and AMPP reference requirements
4. All acceptance criteria are checked off
5. No API key appears in any committed file

---

*Document prepared by PM Agent — Site Audit Agent Project*
*Contact: greggrodgers.ii@gmail.com*
