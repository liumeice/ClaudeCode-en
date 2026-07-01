#!/usr/bin/env python3
"""
Step 2 (multi-threaded): Generate individual PDFs for each Claude Code Docs page + a cover PDF.

Reads sidebar.json, visits each page with Playwright, applies DOM manipulation
to remove navigation/sidebar/TOC, and exports to PDF.

Each worker owns a Playwright browser instance. Pages within a worker share
a single browser context to keep memory bounded.

Usage:
  source .venv/Scripts/activate
  python step2_generate_pdfs_mt.py            # auto-detect CPU threads
  python step2_generate_pdfs_mt.py --workers 8 # explicit worker count
"""

import argparse
import json
import os
import sys
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = 'https://code.claude.com'
ORIGIN = 'https://code.claude.com'

# Reuse the same DOM manipulation JS from the single-threaded version
DOM_MANIPULATE_JS = """
function() {
  document.querySelectorAll('[class*="pt-40"], [class*="pt-32"]').forEach(function(el) {
    var c = el.getAttribute('class') || '';
    if (c.indexOf('pt-40') >= 0 || c.indexOf('pt-32') >= 0) {
      el.style.setProperty('padding-top', '0', 'important');
    }
  });
  document.querySelectorAll('header.fixed, header.sticky, header.z-30').forEach(function(el) {
    el.style.setProperty('position', 'relative', 'important');
    el.style.setProperty('top', 'auto', 'important');
  });
  document.querySelectorAll('nav#sidebar, aside[role="navigation"], #sidebar-content').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });
  document.querySelectorAll('[class*="backdrop"], [id*="backdrop"]').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });
  document.querySelectorAll('ul.toc, .toc, [class*="tableOfContents"], [class*="tocCollapsible"], aside[aria-label="On this page"]').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });
  document.querySelectorAll('*').forEach(function(el) {
    var text = el.textContent || '';
    if ((text === '复制页面' || text === 'Copy page' || text === 'Copy')
        && el.offsetHeight > 0 && el.offsetHeight < 50) {
      el.style.setProperty('display', 'none', 'important');
    }
  });
  document.querySelectorAll('pre button, [class*="copy"] button, .copy-button').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });
  document.querySelectorAll('footer.advanced-footer, footer[role="contentinfo"]').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });
  document.querySelectorAll('*').forEach(function(el) {
    var text = el.textContent || '';
    if ((text.includes('Was this page helpful') || text.includes('此页面') || text.includes('有帮助吗'))
        && el.offsetHeight < 300 && el.offsetHeight > 20) {
      el.style.setProperty('display', 'none', 'important');
    }
  });
  document.querySelectorAll('[class*="feedback"]').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });
  document.querySelectorAll('[class*="assistant-bar"], [class*="chat-assistant"]').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });
  document.querySelectorAll('[class*="pagination"], [class*="prevNext"], [class*="footer-nav"]').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });
  document.querySelectorAll('a').forEach(function(a) {
    var parent = a.parentElement;
    if (!parent) return;
    var cls = parent.getAttribute('class') || '';
    if (cls.indexOf('px-0') >= 0 && cls.indexOf('flex') >= 0 && cls.indexOf('items-center') >= 0 &&
        cls.indexOf('text-sm') >= 0 && cls.indexOf('font-semibold') >= 0 && cls.indexOf('text-gray-700') >= 0) {
      parent.style.setProperty('display', 'none', 'important');
    }
  });
  document.querySelectorAll('*').forEach(function(el) {
    var text = el.textContent || '';
    if ((text.trim() === '编辑此页' || text.trim() === 'Edit this page')
        && el.offsetHeight > 0 && el.offsetHeight < 50) {
      el.style.setProperty('display', 'none', 'important');
    }
  });
  (function() {
    var mdDiv = document.querySelector('.mdx-content, .prose, [class*="markdown"]');
    if (!mdDiv) return;
    function isFrontmatter(t) {
      if (!t) return false;
      return t.indexOf('sidebar_label') >= 0 ||
             t.indexOf('sidebar_position') >= 0 ||
             t.indexOf('description:') >= 0 ||
             /^P?---/.test(t) ||
             (t.indexOf('---') >= 0 && t.indexOf('title:') >= 0);
    }
    var node = mdDiv.firstChild;
    while (node) {
      var nextSibling = node.nextSibling;
      if (node.nodeType === 3) {
        var t = node.textContent || '';
        if (t.trim().length > 0 && isFrontmatter(t)) {
          var span = document.createElement('span');
          span.style.setProperty('display', 'none', 'important');
          span.textContent = t;
          if (node.parentNode) node.parentNode.replaceChild(span, node);
        }
      } else if (node.nodeType === 1) {
        var tag = node.tagName;
        if (tag === 'H2' || tag === 'H3' || tag === 'H4') {
          var headingText = (node.textContent || '').trim();
          if (isFrontmatter(headingText)) {
            node.style.setProperty('display', 'none', 'important');
          }
        }
      }
      node = nextSibling;
    }
  })();
  var tabLists = document.querySelectorAll('[role="tablist"], .tabs, [class*="tabs__"]');
  for (var t = 0; t < tabLists.length; t++) {
    var tabList = tabLists[t];
    var container = tabList.closest('.tabs-container') || tabList.parentElement;
    var tabPanels = container
      ? container.querySelectorAll('[role="tabpanel"]')
      : document.querySelectorAll('[role="tabpanel"]');
    var tabs = tabList.querySelectorAll('[role="tab"]');
    var tabNames = [];
    for (var ti = 0; ti < tabs.length; ti++) tabNames.push(tabs[ti].textContent.trim());
    var tabHtmls = [];
    for (var pi = 0; pi < tabPanels.length; pi++) tabHtmls.push(tabPanels[pi].innerHTML);
    tabList.style.setProperty('display', 'none', 'important');
    for (var pi = 0; pi < tabPanels.length; pi++) tabPanels[pi].style.setProperty('display', 'none', 'important');
    for (var ti = 0; ti < tabHtmls.length; ti++) {
      var section = document.createElement('div');
      section.setAttribute('data-tab-expanded', tabNames[ti]);
      section.style.cssText = 'margin-top: 20px; margin-bottom: 25px; padding: 15px 0; display: block !important;';
      var heading = document.createElement('div');
      heading.style.cssText = 'font-size: 14px; font-weight: 600; margin-bottom: 12px; padding: 6px 0 8px 0; border-bottom: 2px solid #e5e7eb;';
      heading.textContent = tabNames[ti];
      section.appendChild(heading);
      var cc = document.createElement('div');
      cc.style.cssText = 'display: block !important; opacity: 1 !important;';
      cc.innerHTML = tabHtmls[ti];
      var allEls = cc.querySelectorAll('*');
      for (var ci = 0; ci < allEls.length; ci++) {
        if (allEls[ci].classList) {
          allEls[ci].classList.remove('hidden');
          allEls[ci].classList.remove('sr-only');
          allEls[ci].classList.remove('opacity-0');
        }
      }
      section.appendChild(cc);
      tabList.parentNode.insertBefore(section, tabList);
    }
  }
  document.querySelectorAll('img').forEach(function(el) {
    if (el.src) {
      el.onerror = function() {
        if (el._retried) return;
        el._retried = true;
        var src = el.getAttribute('src');
        if (src && src.indexOf('/zh-CN/') >= 0) {
          el.src = src.replace('/zh-CN/', '/');
        }
        if (src && src.indexOf('/en/') >= 0 && !el.src.startsWith('http')) {
          el.src = src.replace('/en/', '/');
        }
      };
    }
  });
  document.querySelectorAll('img').forEach(function(el) {
    var rect = el.getBoundingClientRect();
    var hAttr = parseInt(el.getAttribute('height'), 10) || 0;
    var isTall = rect.height > 600 || hAttr > 600;
    if (!isTall) return;
    var node = el.parentElement;
    for (var i = 0; i < 6 && node; i++) {
      var cs = window.getComputedStyle(node);
      if (cs.overflow === 'hidden' || cs.overflowY === 'hidden') {
        node.style.setProperty('overflow', 'visible', 'important');
        node.style.setProperty('overflow-y', 'visible', 'important');
      }
      node = node.parentElement;
    }
    el.style.setProperty('max-width', '100%', 'important');
    el.style.setProperty('max-height', '270mm', 'important');
    el.style.setProperty('width', 'auto', 'important');
    el.style.setProperty('height', 'auto', 'important');
    el.style.setProperty('object-fit', 'contain', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('margin', '0 auto', 'important');
    el.style.setProperty('break-inside', 'avoid', 'important');
    el.style.setProperty('page-break-inside', 'avoid', 'important');
  });
  var bgStyle = document.createElement('style');
  bgStyle.textContent = [
    'html, body { background-color: #FFFFFF !important; }',
    '@page { margin: 5mm 0 5mm 0; background-color: #FFFFFF; }',
    'pre, code { white-space: pre-wrap !important; overflow-wrap: anywhere !important; max-width: 100% !important; }',
    '* { orphans: 1 !important; widows: 1 !important; }',
    'h1,h2,h3,h4,h5,h6 { break-after: avoid !important; page-break-after: avoid !important; }',
    '.flex.flex-row-reverse { display: block !important; }',
  ].join('');
  document.head.appendChild(bgStyle);
  document.querySelectorAll('*').forEach(function(el) {
    var bg = window.getComputedStyle(el).backgroundColor;
    var tag = el.tagName;
    var cls = el.getAttribute('class') || '';
    if (tag === 'CODE' || tag === 'PRE' ||
        cls.indexOf('callout') >= 0 || cls.indexOf('prose') >= 0 ||
        cls.indexOf('code') >= 0 || cls.indexOf('block') >= 0 ||
        tag === 'TABLE' || tag === 'TD' || tag === 'TH' || tag === 'TR' ||
        tag === 'THEAD' || tag === 'TBODY') {
      return;
    }
    if (bg === 'rgb(253, 253, 247)' || bg === 'rgb(250, 250, 250)' || bg === 'rgb(249, 250, 251)' ||
        bg === 'rgb(248, 249, 250)' || bg === 'rgb(245, 245, 245)') {
      el.style.setProperty('background-color', '#FFFFFF', 'important');
    }
  });
  document.querySelectorAll('details, [class*="accordion"]').forEach(function(el) {
    var bg = window.getComputedStyle(el).backgroundColor;
    if (bg === 'rgb(253, 253, 247)' || bg === 'rgb(250, 250, 250)' || bg === 'rgb(249, 250, 251)' ||
        bg === 'rgb(248, 249, 250)' || bg === 'rgb(245, 245, 245)') {
      el.style.setProperty('background-color', '#FFFFFF', 'important');
    }
  });
  document.body.style.setProperty('height', 'auto', 'important');
  document.body.style.setProperty('min-height', 'auto', 'important');
  document.documentElement.style.setProperty('height', 'auto', 'important');
  document.documentElement.style.setProperty('min-height', 'auto', 'important');
}
"""


# ============================================================
# Cover page HTML (same as single-threaded version)
# ============================================================
def generate_cover_html(total_pages):
    now = datetime.now()
    edition = f'{now.year}·{now.month:02d}'
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: 210mm; height: 297mm; overflow: hidden; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; color: #fff; }}
  .page {{ width: 210mm; height: 297mm; position: relative; overflow: hidden; background: linear-gradient(180deg, #CC876C 0%, #C77C5E 100%); }}
  .geo-lines {{ position: absolute; inset: 0; opacity: 0.06; }}
  .geo-lines svg {{ width: 100%; height: 100%; }}
  .center-wrap {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
  .content {{ display: flex; flex-direction: column; align-items: center; text-align: center; }}
  .top-rule {{ width: 32px; height: 1px; background: rgba(255,255,255,0.35); margin-bottom: 40px; }}
  .brand-label {{ font-size: 11px; font-weight: 400; letter-spacing: 6px; text-transform: uppercase; color: rgba(255,255,255,0.5); margin-bottom: 36px; }}
  .title {{ font-size: 56px; font-weight: 300; line-height: 1.1; margin-bottom: 8px; letter-spacing: 2px; }}
  .title em {{ font-style: normal; font-weight: 700; }}
  .title-sub {{ font-size: 24px; font-weight: 300; color: rgba(255,255,255,0.8); margin-bottom: 44px; letter-spacing: 6px; }}
  .divider-wrap {{ display: flex; align-items: center; gap: 12px; margin-bottom: 44px; }}
  .divider-line {{ width: 28px; height: 0.5px; background: rgba(255,255,255,0.3); }}
  .divider-diamond {{ width: 5px; height: 5px; background: rgba(255,255,255,0.4); transform: rotate(45deg); }}
  .edition {{ display: flex; align-items: center; gap: 14px; margin-bottom: 52px; }}
  .edition-line {{ width: 24px; height: 0.5px; background: rgba(255,255,255,0.25); }}
  .edition-text {{ font-size: 15px; font-weight: 400; color: rgba(255,255,255,0.75); letter-spacing: 2px; }}
  .features {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 8px 18px; max-width: 460px; margin-bottom: 56px; }}
  .feature-tag {{ font-size: 11px; font-weight: 400; color: rgba(255,255,255,0.55); padding: 4px 12px; border: 0.5px solid rgba(255,255,255,0.2); letter-spacing: 0.5px; }}
  .bottom-rule {{ position: absolute; bottom: 60px; left: 0; right: 0; display: flex; justify-content: center; }}
  .bottom-rule-line {{ width: 32px; height: 1px; background: rgba(255,255,255,0.2); }}
  .bottom-info {{ position: absolute; bottom: 28px; left: 0; right: 0; text-align: center; }}
  .bottom-url {{ font-size: 11px; color: rgba(255,255,255,0.35); letter-spacing: 1.5px; margin-bottom: 5px; }}
  .bottom-copy {{ font-size: 9px; color: rgba(255,255,255,0.2); letter-spacing: 0.5px; }}
  .corner {{ position: absolute; width: 24px; height: 24px; opacity: 0.12; }}
  .corner svg {{ width: 100%; height: 100%; }}
  .corner-tl {{ top: 28px; left: 28px; }}
  .corner-tr {{ top: 28px; right: 28px; transform: scaleX(-1); }}
  .corner-bl {{ bottom: 28px; left: 28px; transform: scaleY(-1); }}
  .corner-br {{ bottom: 28px; right: 28px; transform: scale(-1,-1); }}
</style></head>
<body>
<div class="page">
  <div class="geo-lines"><svg viewBox="0 0 794 1123" fill="none"><line x1="0" y1="374" x2="794" y2="374" stroke="#fff" stroke-width="0.5"/><line x1="0" y1="748" x2="794" y2="748" stroke="#fff" stroke-width="0.5"/><line x1="264" y1="0" x2="264" y2="1123" stroke="#fff" stroke-width="0.5"/><line x1="530" y1="0" x2="530" y2="1123" stroke="#fff" stroke-width="0.5"/><circle cx="397" cy="561" r="180" stroke="#fff" stroke-width="0.5"/><circle cx="397" cy="561" r="280" stroke="#fff" stroke-width="0.3"/></svg></div>
  <div class="corner corner-tl"><svg viewBox="0 0 24 24"><path d="M0 24V0h24" stroke="#fff" stroke-width="1" fill="none"/></svg></div>
  <div class="corner corner-tr"><svg viewBox="0 0 24 24"><path d="M0 24V0h24" stroke="#fff" stroke-width="1" fill="none"/></svg></div>
  <div class="corner corner-bl"><svg viewBox="0 0 24 24"><path d="M0 24V0h24" stroke="#fff" stroke-width="1" fill="none"/></svg></div>
  <div class="corner corner-br"><svg viewBox="0 0 24 24"><path d="M0 24V0h24" stroke="#fff" stroke-width="1" fill="none"/></svg></div>
  <div class="center-wrap"><div class="content">
    <div class="top-rule"></div>
    <div class="brand-label">Anthropic</div>
    <div class="title"><em>Claude</em> Code</div>
    <div class="title-sub">Official Documentation</div>
    <div class="divider-wrap"><span class="divider-line"></span><span class="divider-diamond"></span><span class="divider-line"></span></div>
    <div class="edition"><span class="edition-line"></span><span class="edition-text">{edition}</span><span class="edition-line"></span></div>
    <div class="features"><span class="feature-tag">Quick Start</span><span class="feature-tag">Core Concepts</span><span class="feature-tag">Agent Mode</span><span class="feature-tag">MCP Protocol</span><span class="feature-tag">Agent SDK</span><span class="feature-tag">Best Practices</span></div>
  </div></div>
  <div class="bottom-rule"><span class="bottom-rule-line"></span></div>
  <div class="bottom-info"><div class="bottom-url">code.claude.com/docs</div><div class="bottom-copy">Generated by liumc</div></div>
</div>
</body></html>"""


def flatten_pages(tree, pages=None):
    """Flatten the sidebar tree into a list of leaf page dicts."""
    if pages is None:
        pages = []
    for node in tree:
        if 'children' not in node or not node['children']:
            pages.append(node)
        else:
            flatten_pages(node['children'], pages)
    return pages


def url_to_filename(url):
    """Convert a URL to a safe filename."""
    path = url.replace(ORIGIN, '').replace('https://', '').replace('http://', '')
    return path.replace('/', '_').replace('?', '_').replace('#', '_').replace(' ', '_')[:80]


def generate_cover_pdf(output_path, total_pages):
    """Generate cover page PDF using Playwright."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 794, 'height': 1123})
        page = context.new_page()
        page.set_content(generate_cover_html(total_pages), wait_until='domcontentloaded', timeout=10000)
        page.wait_for_timeout(500)
        page.pdf(
            path=output_path,
            format='A4',
            print_background=True,
            margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'},
        )
        browser.close()
    print(f'  Generated: {output_path}')


def worker_convert(worker_id, work_queue, results, pdfs_dir):
    """
    Worker function: owns one Playwright browser instance, processes pages
    from the shared queue until exhausted.

    Parameters
    ----------
    worker_id : int
        Worker index (for logging).
    work_queue : list
        Shared list of (idx, total, page_data) tuples. Acts as a work queue.
    results : dict
        Thread-safe dict-like to collect per-item results (keyed by idx).
    pdfs_dir : Path
        Output directory for PDFs.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        )

        while True:
            try:
                item = work_queue.pop(0)
            except IndexError:
                break

            idx, total, page_data = item
            title = page_data['title']
            href = page_data['href']
            url = f'{ORIGIN}{href}'
            filename = url_to_filename(url) + '.pdf'
            output_path = pdfs_dir / filename

            if output_path.exists() and output_path.stat().st_size > 0:
                results[idx] = ('skipped', title, 0)
                continue

            page = context.new_page()
            try:
                try:
                    page.goto(url, wait_until='networkidle', timeout=60000)
                except Exception:
                    pass
                page.wait_for_timeout(3000)

                # Check for 404
                is_404 = page.evaluate('''() => {
                    var h1 = document.querySelector('h1');
                    return h1 && h1.textContent && (h1.textContent.includes('404') || h1.textContent.includes('Not Found'));
                }''')
                if is_404:
                    page.close()
                    results[idx] = ('failed', title, 0)
                    continue

                page.evaluate(DOM_MANIPULATE_JS)
                page.wait_for_timeout(3000)

                page.pdf(
                    path=str(output_path),
                    format='A4',
                    print_background=True,
                    margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'},
                )

                size_kb = output_path.stat().st_size / 1024 if output_path.exists() else 0
                page.close()
                results[idx] = ('ok', title, size_kb)
            except Exception as e:
                try:
                    page.close()
                except Exception:
                    pass
                results[idx] = ('failed', title, 0)

        context.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser(
        description='Step 2 (multi-threaded): Generate individual PDFs for each Claude Code Docs page.'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=0,
        help='Number of parallel workers. 0 = auto-detect CPU thread count (default: 0)',
    )
    args = parser.parse_args()

    # Auto-detect CPU threads
    import multiprocessing
    cpu_count = multiprocessing.cpu_count()
    workers = args.workers if args.workers > 0 else cpu_count

    print('Step 2 (multi-threaded): Generating individual PDFs')
    print(f'  CPU threads: {cpu_count}, workers: {workers}')
    print()

    # Load sidebar
    with open('sidebar.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    pages = flatten_pages(data['children'])
    total = len(pages)
    print(f'  Total pages to convert: {total}')

    # Create output directories
    pdfs_dir = Path('temp/pdfs')
    cover_dir = Path('Output/temp')
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    cover_dir.mkdir(parents=True, exist_ok=True)

    # Generate cover PDF
    cover_path = cover_dir / 'Cover_Claude_Code.pdf'
    if not cover_path.exists():
        print('  Generating cover page...')
        generate_cover_pdf(str(cover_path), total)
    else:
        print('  Cover already exists, skipping.')
    print()

    # Build work queue: shared list consumed by workers
    work_queue = [(idx, total, page_data) for idx, page_data in enumerate(pages, 1)]
    results = {}  # idx -> (status, title, size_kb)

    # Launch workers
    print(f'  Launching {workers} workers...')
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for wid in range(workers):
            f = executor.submit(worker_convert, wid, work_queue, results, pdfs_dir)
            futures.append(f)
        # Wait for all workers to finish
        for f in as_completed(futures):
            f.result()  # re-raise any worker exceptions

    elapsed = time.time() - t0

    # Aggregate results in original order
    success = 0
    skipped = 0
    failed = 0

    for idx in range(1, total + 1):
        status, title, size_kb = results.get(idx, ('failed', pages[idx - 1]['title'], 0))
        if status == 'ok':
            print(f'    [{idx:3d}/{total}] {title:<50s} {size_kb:>8.1f} KB')
            success += 1
        elif status == 'skipped':
            print(f'    [{idx:3d}/{total}] ⏭ Skip: {title}')
            skipped += 1
        else:
            print(f'    [{idx:3d}/{total}] {title:<50s} FAILED')
            failed += 1

    print()
    print(f'  Summary: {success} generated, {skipped} skipped, {failed} failed')
    print(f'  Time elapsed: {elapsed:.1f}s')
    print(f'  Output directory: {pdfs_dir}/')


if __name__ == '__main__':
    main()
