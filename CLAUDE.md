# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Claude Code Docs PDF Generator** — A 3-step Python pipeline that scrapes the Claude Code documentation website (code.claude.com/docs/en/) and converts it into a single merged PDF with full bookmark/navigation structure.

## Quick Start

```bash
# Activate virtual environment
.venv\Scripts\activate.bat

# Run full pipeline
run.bat

# Or run individual steps
run.bat step1   # Scrape sidebar navigation structure
run.bat step2   # Generate individual page PDFs
run.bat step3   # Merge all PDFs into one with bookmarks
```

## Architecture

The pipeline is a 3-stage sequential process. Each step produces artifacts consumed by the next:

```
[Website] → step1 → sidebar.json → step2 → temp/pdfs/*.pdf → step3 → Output/ClaudeCodeDocs.pdf
```

### Step 1: Scrape Sidebar ([step1_scrape_sidebar.py](step1_scrape_sidebar.py))

- Uses Playwright (headless Chromium) to visit each top-level nav tab on the docs site
- Extracts sidebar group/page structure via DOM scraping (`#sidebar-content`, `nav#sidebar`)
- Outputs:
  - `sidebar.json` — hierarchical tree `{title, href, level, children}`
  - `sidebar.md` — human-readable Markdown table of contents

### Step 2: Generate PDFs ([step2_generate_pdfs.py](step2_generate_pdfs.py))

- Reads `sidebar.json`, flattens the tree into a list of leaf pages
- For each page: visits URL with Playwright, applies extensive DOM manipulation to remove nav/sidebar/TOC/feedback widgets, fixes image paths, expands tab components, normalizes backgrounds
- Outputs individual PDFs to `temp/pdfs/<url_sanitized>.pdf`
- Generates a styled cover page PDF at `Output/temp/Cover_Claude_Code.pdf`
- Skips already-generated PDFs (idempotent)

### Step 3: Merge PDFs ([step3_merge_pdfs.py](step3_merge_pdfs.py))

- Reads `sidebar.json` for bookmark hierarchy and `temp/pdfs/` for individual PDFs
- Uses PyMuPDF (`fitz`) to merge all PDFs in navigation order
- Builds a precise table of contents with correct page offsets (categories point to their first child's starting page)
- Outputs: `Output/ClaudeCodeDocs.pdf`

## Dependencies

Managed via `.venv` virtual environment. Key packages in [requirements.txt](requirements.txt):

- `playwright` — headless browser automation (scraping + PDF export)
- `PyMuPDF` — PDF manipulation and merging

Install dependencies: `.venv\Scripts\python.exe -m pip install -r requirements.txt`

## Key Implementation Details

- **DOM manipulation** (step 2): Inline JavaScript in `step2_generate_pdfs.py` handles Tailwind-based layout quirks — hides sidebar/TOC/footer/feedback, fixes spacing, expands hidden tab panels, normalizes cream backgrounds to white, sets print-friendly CSS
- **Idempotency**: Step 2 skips PDFs that already exist; step 3 regenerates from whatever PDFs are in `temp/pdfs/`
- **URL-to-filename mapping**: URLs are sanitized by replacing `/` with `_` and truncating to 80 chars
- **Encoding**: All scripts wrap `sys.stdout` with `utf-8` encoding for Windows console compatibility
- **Lazy-load handling**: Step 1 scrolls the sidebar to bottom before extracting to trigger lazy-loaded content
