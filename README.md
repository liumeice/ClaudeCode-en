# Claude Code Docs PDF Generator

A 3-step Python pipeline that scrapes the [Claude Code documentation website](https://code.claude.com/docs/en/) and converts it into a single merged PDF with full bookmark/navigation structure.

## Output

The final PDF is generated at `Output/ClaudeCodeDocs.pdf` — a complete, navigable offline copy of the Claude Code docs with a clickable table of contents.

## Quick Start

```bat
# Activate the virtual environment
.venv\Scripts\activate.bat

# Run the full pipeline
run.bat

# Or run individual steps
run.bat step1   REM Scrape sidebar navigation structure
run.bat step2   REM Generate individual page PDFs
run.bat step3   REM Merge all PDFs into one with bookmarks
```

## Pipeline Architecture

```
[Website] ──step1──> sidebar.json ──step2──> temp/pdfs/*.pdf ──step3──> Output/ClaudeCodeDocs.pdf
```

Each step produces artifacts consumed by the next:

### Step 1 — Scrape Sidebar

**Script:** `step1_scrape_sidebar.py`

Uses Playwright (headless Chromium) to visit each top-level nav tab on the docs site and extract the sidebar group/page structure via DOM scraping (`#sidebar-content`, `nav#sidebar`). Scrolls to the bottom of the sidebar before extracting to trigger lazy-loaded content.

**Outputs:**
| File | Description |
|---|---|
| `sidebar.json` | Hierarchical tree `{title, href, level, children}` |
| `sidebar.md` | Human-readable Markdown table of contents |

### Step 2 — Generate PDFs

**Script:** `step2_generate_pdfs.py`

Reads `sidebar.json`, flattens the tree into a list of leaf pages, then for each page: visits the URL with Playwright, applies extensive DOM manipulation to produce clean print-ready pages, and exports a PDF.

**DOM manipulation includes:**
- Hides nav bars, sidebar, TOC, footer, and feedback widgets
- Fixes Tailwind-based layout spacing quirks
- Expands hidden tab components so all content is visible
- Normalizes cream backgrounds to white
- Fixes image paths for local rendering
- Sets print-friendly CSS

Also generates a styled cover page PDF at `Output/temp/Cover_Claude_Code.pdf`.

**Outputs:** Individual PDFs to `temp/pdfs/<url_sanitized>.pdf` (URLs are sanitized by replacing `/` with `_` and truncating to 80 chars).

Step 2 is **idempotent** — it skips PDFs that already exist, so you can re-run it after fixing issues without regenerating everything.

### Step 3 — Merge PDFs

**Script:** `step3_merge_pdfs.py`

Reads `sidebar.json` for the bookmark hierarchy and `temp/pdfs/` for the individual PDF files. Uses PyMuPDF (`fitz`) to merge all PDFs in navigation order and builds a precise table of contents with correct page offsets (category entries point to their first child's starting page).

**Output:** `Output/ClaudeCodeDocs.pdf`

## Prerequisites

- **Python 3.10+**
- **Playwright browsers** — after installing dependencies, run:

  ```bat
  .venv\Scripts\python.exe -m playwright install chromium
  ```

## Dependencies

Managed via the `.venv` virtual environment:

| Package | Purpose |
|---|---|
| `playwright==1.60.0` | Headless browser automation (scraping + PDF export) |
| `PyMuPDF==1.27.2` | PDF manipulation and merging |

Install dependencies:

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Directory Structure

```
.
├── step1_scrape_sidebar.py    # Sidebar scraper
├── step2_generate_pdfs.py     # PDF generator
├── step3_merge_pdfs.py        # PDF merger
├── run.bat                    # Pipeline runner script
├── requirements.txt           # Python dependencies
├── sidebar.json               # [generated] Nav structure tree
├── sidebar.md                 # [generated] Human-readable TOC
├── .venv/                     # Python virtual environment
├── temp/
│   └── pdfs/                  # [generated] Individual page PDFs
└── Output/
    ├── temp/
    │   └── Cover_Claude_Code.pdf  # [generated] Cover page
    └── ClaudeCodeDocs.pdf         # [final] Merged output
```

## Notes

- **Windows console encoding:** All scripts wrap `sys.stdout` with UTF-8 encoding for Windows compatibility.
- **Re-running after failures:** If step 2 fails partway through, just re-run it — already-generated PDFs will be skipped.
- **Partial updates:** If the docs site changes, you can re-run individual steps without rebuilding everything from scratch.
