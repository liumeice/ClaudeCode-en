#!/usr/bin/env python3
"""
Step 2: Generate individual PDFs for each Claude Code Docs page + a cover PDF.

Reads sidebar.json, visits each page with Playwright, applies DOM manipulation
to remove navigation/sidebar/TOC, and exports to PDF.

Usage:
  source .venv/Scripts/activate
  python step2_generate_pdfs.py
"""

import json
import os
import sys
import io
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = 'https://code.claude.com'
ORIGIN = 'https://code.claude.com'

# ============================================================
# DOM manipulation script for Claude Code Docs (Tailwind-based)
# ============================================================
DOM_MANIPULATE_JS = """
function() {
  // === Keep top nav bar and icons, hide unwanted elements ===

  // 0. Remove dark-mode-only image variants (Mintlify dual images).
  //    Every diagram is paired: light version (class "dark:mint-hidden",
  //    visible in light mode) + dark version (class "mint-hidden" with
  //    "dark:mint-block", display:none in light mode). The PDF renders in
  //    light mode, so delete the dark variants up front — otherwise later
  //    steps (e.g. 11b forcing display:block on tall images) can un-hide
  //    them and print both variants side by side.
  document.querySelectorAll('img').forEach(function(el) {
    if (el.classList.contains('mint-hidden') && !el.classList.contains('dark:mint-hidden')) {
      el.remove();
    }
  });

  // 1. Compress vertical spacing in the main content area
  //    (diagnosed: pt-[calc(10rem+...)] = 160px+ computed, mt-8 = 32px, mb-14 = 32px,
  //     h2 mt = 36px, code blocks mt-5/mb-8 = 20/32px, card grids mt-6/mt-8 = 24/32px)

  // 1a. Main content wrapper: the huge top padding pt-[calc(10rem+var(--banner-height,...))]
  //     and lg:pt-10 / pt-10 all create 40px-160px of top padding. Reduce to a small value.
  document.querySelectorAll('[class*="pt-"]').forEach(function(el) {
    var cls = el.getAttribute('class') || '';
    // Match: pt-[calc(...)], pt-[XXrem], pt-[XXpx] (arbitrary values)
    if (/pt-\[/.test(cls)) {
      el.style.setProperty('padding-top', '16px', 'important');
    }
  });
  // pt-10 (40px), pt-12 (48px), pt-16 (64px), pt-20 (80px), pt-24 (96px),
  // pt-28 (112px), pt-32 (128px), pt-36 (144px), pt-40 (160px)
  // Keep pt-0..pt-4 (0-16px) alone; reduce anything larger.
  var largePT = ['pt-10','pt-12','pt-14','pt-16','pt-20','pt-24','pt-28','pt-32','pt-36','pt-40','pt-44','pt-48','pt-52','pt-56','pt-60','pt-64','pt-72','pt-80','pt-96'];
  largePT.forEach(function(c) {
    document.querySelectorAll('.' + c).forEach(function(el) {
      // Only override if not already set via style above (arbitrary values)
      if (el.style.paddingTop !== '16px') {
        el.style.setProperty('padding-top', '8px', 'important');
      }
    });
  });

  // 1b. Scroll area inner: pt-10 (40px) + pb-4 (16px) → compact
  ['pt-10','pt-8','pt-12','pt-14','pt-16'].forEach(function(c) {
    document.querySelectorAll('.' + c).forEach(function(el) {
      if (el.style.paddingTop !== '16px') {
        el.style.setProperty('padding-top', '4px', 'important');
      }
    });
  });
  ['pb-4','pb-6','pb-8','pb-10','pb-12'].forEach(function(c) {
    document.querySelectorAll('.' + c).forEach(function(el) {
      el.style.setProperty('padding-bottom', '4px', 'important');
    });
  });

  // 1c. Content area (.mdx-content): mt-8 (32px) + mb-14 (32px) → compact
  document.querySelectorAll('[class*="mdx-content"]').forEach(function(el) {
    el.style.setProperty('margin-top', '8px', 'important');
    el.style.setProperty('margin-bottom', '8px', 'important');
  });
  // Generic mt-8, mb-14 on non-content elements too
  ['mt-8','mt-10','mt-12','mt-14','mt-16','mt-20','mt-24'].forEach(function(c) {
    document.querySelectorAll('.' + c).forEach(function(el) {
      if (!el.classList.contains('mdx-content')) {
        el.style.setProperty('margin-top', '8px', 'important');
      }
    });
  });
  ['mb-8','mb-10','mb-12','mb-14','mb-16','mb-20','mb-24'].forEach(function(c) {
    document.querySelectorAll('.' + c).forEach(function(el) {
      if (!el.classList.contains('mdx-content')) {
        el.style.setProperty('margin-bottom', '8px', 'important');
      }
    });
  });

  // 1d. py-* and my-* classes (padding-y / margin-y) — reduce vertical padding
  //     py-10=40px, py-12=48px, py-16=64px, py-20=80px, py-28=112px
  ['py-8','py-10','py-12','py-14','py-16','py-20','py-24','py-28','py-32'].forEach(function(c) {
    document.querySelectorAll('.' + c).forEach(function(el) {
      el.style.setProperty('padding-top', '8px', 'important');
      el.style.setProperty('padding-bottom', '8px', 'important');
    });
  });
  // Arbitrary py-[calc(...)], py-[XXrem] etc.
  document.querySelectorAll('[class*="py-["]').forEach(function(el) {
    el.style.setProperty('padding-top', '8px', 'important');
    el.style.setProperty('padding-bottom', '8px', 'important');
  });
  ['my-8','my-10','my-12','my-14','my-16','my-20','my-24','my-28','my-32'].forEach(function(c) {
    document.querySelectorAll('.' + c).forEach(function(el) {
      el.style.setProperty('margin-top', '4px', 'important');
      el.style.setProperty('margin-bottom', '4px', 'important');
    });
  });

  // 1e. Special components: ssc-root (settings comparison), callouts, tables
  document.querySelectorAll('.ssc-root, [class*="ssc-"]').forEach(function(el) {
    el.style.setProperty('margin-top', '8px', 'important');
    el.style.setProperty('margin-bottom', '8px', 'important');
    el.style.setProperty('padding-top', '8px', 'important');
    el.style.setProperty('padding-bottom', '8px', 'important');
  });

  // 1e1. Callout icon–text alignment: the icon wrapper has mt-0.5 (2px top margin)
  //       and the flex container defaults to align-items:stretch, causing the icon
  //       to sit lower than the first text line. Fix by top-aligning the flex items
  //       and zeroing the icon wrapper's top margin.
  document.querySelectorAll('.callout, [role="note"], [role="alert"], [role="warning"], [role="danger"], [role="info"], [role="tip"]').forEach(function(el) {
    var cs = window.getComputedStyle(el);
    if (cs.display === 'flex' || cs.display === 'inline-flex') {
      el.style.setProperty('align-items', 'flex-start', 'important');
    }
  });
  document.querySelectorAll('[data-component-part="callout-icon"]').forEach(function(el) {
    el.style.setProperty('transform', 'translateY(1px)', 'important');
  });
  // The content div has mt-2 (8px) pushing it below the icon; zero it too.
  document.querySelectorAll('[data-component-part="callout-content"]').forEach(function(el) {
    el.style.setProperty('margin-top', '0', 'important');
  });

  // 1f. Card grid items: mt-6 (24px) / lg:mt-8 (32px) → compact
  ['mt-6','mt-7'].forEach(function(c) {
    document.querySelectorAll('.' + c).forEach(function(el) {
      if (!el.classList.contains('mdx-content')) {
        el.style.setProperty('margin-top', '8px', 'important');
      }
    });
  });

  // 1f. Code blocks: mt-5 (20px) + mb-8 (32px) → compact
  document.querySelectorAll('[class*="code-block"]').forEach(function(el) {
    el.style.setProperty('margin-top', '8px', 'important');
    el.style.setProperty('margin-bottom', '8px', 'important');
  });

  // 1g. Section headings (h2, h3): browser default mt ~32-36px → compact
  document.querySelectorAll('h2, h3').forEach(function(el) {
    el.style.setProperty('margin-top', '16px', 'important');
    el.style.setProperty('margin-bottom', '8px', 'important');
  });

  // Fix top nav bar to relative positioning (avoid overlap in PDF)
  document.querySelectorAll('header.fixed, header.sticky, header.z-30').forEach(function(el) {
    el.style.setProperty('position', 'relative', 'important');
    el.style.setProperty('top', 'auto', 'important');
  });

  // 2. Hide left sidebar
  document.querySelectorAll('nav#sidebar, aside[role="navigation"], #sidebar-content').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });

  // Hide backdrop overlay
  document.querySelectorAll('[class*="backdrop"], [id*="backdrop"]').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });

  // 3. Hide right TOC
  document.querySelectorAll('ul.toc, .toc, [class*="tableOfContents"], [class*="tocCollapsible"], aside[aria-label="On this page"]').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });

  // 4. Hide "Copy page" button
  document.querySelectorAll('*').forEach(function(el) {
    var text = el.textContent || '';
    if ((text === '复制页面' || text === 'Copy page' || text === 'Copy')
        && el.offsetHeight > 0 && el.offsetHeight < 50) {
      el.style.setProperty('display', 'none', 'important');
    }
  });

  // Hide copy buttons in code blocks
  document.querySelectorAll('pre button, [class*="copy"] button, .copy-button').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });

  // 5. Hide footer/feedback
  document.querySelectorAll('footer.advanced-footer, footer[role="contentinfo"]').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });

  // Hide feedback widget
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

  // 6. Hide Claude Code AI input bar
  document.querySelectorAll('[class*="assistant-bar"], [class*="chat-assistant"]').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });

  // 7. Hide prev/next article navigation
  document.querySelectorAll('[class*="pagination"], [class*="prevNext"], [class*="footer-nav"]').forEach(function(el) {
    el.style.setProperty('display', 'none', 'important');
  });

  // Hide bottom prev/next nav container (flex row with small text at end of article)
  document.querySelectorAll('a').forEach(function(a) {
    var parent = a.parentElement;
    if (!parent) return;
    var cls = parent.getAttribute('class') || '';
    // Match the specific bottom nav container: "px-0.5 flex items-center text-sm font-semibold text-gray-700"
    if (cls.indexOf('px-0') >= 0 && cls.indexOf('flex') >= 0 && cls.indexOf('items-center') >= 0 &&
        cls.indexOf('text-sm') >= 0 && cls.indexOf('font-semibold') >= 0 && cls.indexOf('text-gray-700') >= 0) {
      parent.style.setProperty('display', 'none', 'important');
    }
  });

  // Remove "Edit this page"
  document.querySelectorAll('*').forEach(function(el) {
    var text = el.textContent || '';
    if ((text.trim() === '编辑此页' || text.trim() === 'Edit this page')
        && el.offsetHeight > 0 && el.offsetHeight < 50) {
      el.style.setProperty('display', 'none', 'important');
    }
  });

  // 8. Frontmatter cleanup
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

  // 9. Expand all <details> / accordion elements (closed by default on many pages)
  document.querySelectorAll('details').forEach(function(el) {
    el.setAttribute('open', '');
    el.open = true;
    // Remove any overflow:hidden or height constraints that might hide content
    el.style.setProperty('overflow', 'visible', 'important');
    el.style.setProperty('max-height', 'none', 'important');
  });

  // 10. Expand tab components (show all tabs sequentially)
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

  // 11. Fix image paths
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

  // 11b. Tall diagrams (e.g. hooks lifecycle, 520x1228 portrait) — taller than a
  //      page and wrapped in overflow:hidden frames, which makes Chromium shrink
  //      the image and emit blank pages. Unconstrain the frame and size the image
  //      to fit one printable page, kept intact with break-inside:avoid.
  document.querySelectorAll('img').forEach(function(el) {
    // Never touch images that are legitimately hidden (e.g. dark-mode
    // variants) — forcing display:block here would print them too.
    if (el.getClientRects().length === 0) return;
    var rect = el.getBoundingClientRect();
    var hAttr = parseInt(el.getAttribute('height'), 10) || 0;
    var isTall = rect.height > 600 || hAttr > 600;
    if (!isTall) return;
    // Walk up and clear overflow:hidden / fixed heights so the image is not clipped
    // or shrunk by object-fit:contain inside a collapsed flex box.
    var node = el.parentElement;
    for (var i = 0; i < 6 && node; i++) {
      var cs = window.getComputedStyle(node);
      if (cs.overflow === 'hidden' || cs.overflowY === 'hidden') {
        node.style.setProperty('overflow', 'visible', 'important');
        node.style.setProperty('overflow-y', 'visible', 'important');
      }
      node = node.parentElement;
    }
    // Size to fit one A4 page (content height ~270mm) and keep it whole on one page.
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

  // 10c. 修复代码块提前换行（必须在下面注入 print CSS 之前执行）。
  //      站点代码块为横向滚动设计，样式表规则
  //        [data-has-floating-buttons] > [data-component-part="code-block-root"] pre > code {
  //          padding-right: var(--code-padding-right, 0px) !important;  (~163px，为浮动按钮预留)
  //        }
  //      在 max-width:100% 收缩后残留盒内（border-box），偷走折行宽度，长行提前约 19 字符折断。
  //      且站点监听 beforeprint 重建代码块 DOM，行内修复会被清掉——因此必须改写
  //      样式表规则本身（CSSOM）。打印时浮动按钮已被隐藏，该预留空间清零是安全的。
  (function() {
    function patchRules(rules) {
      for (var ri = 0; ri < rules.length; ri++) {
        var rule = rules[ri];
        if (rule.cssRules && !(rule instanceof CSSStyleRule)) {
          patchRules(rule.cssRules);
          continue;
        }
        if (!rule.selectorText) continue;
        if (rule.selectorText.indexOf('[data-has-floating-buttons]') >= 0 &&
            rule.style && rule.style.getPropertyValue('padding-right')) {
          rule.style.setProperty('padding-right', '0px', 'important');
        }
      }
    }
    for (var si = 0; si < document.styleSheets.length; si++) {
      var rules;
      try { rules = document.styleSheets[si].cssRules; } catch (e) { continue; }
      patchRules(rules);
    }
  })();

  // 11. Print-only CSS — global spacing overrides as fallback
  var bgStyle = document.createElement('style');
  bgStyle.textContent = [
    'html, body { background-color: #FFFFFF !important; }',
    '@page { margin: 5mm 0 5mm 0; background-color: #FFFFFF; }',
    'pre, code { white-space: pre-wrap !important; overflow-wrap: anywhere !important; max-width: 100% !important; }',
    '* { orphans: 1 !important; widows: 1 !important; }',
    'h1,h2,h3,h4,h5,h6 { break-after: avoid !important; page-break-after: avoid !important; }',
    // Content full-width (sidebar is hidden)
    '.flex.flex-row-reverse { display: block !important; }',
    // Print-level spacing overrides: compress vertical gaps
    // Tailwind scale: pt-1=4px ... pt-10=40px ... pt-16=64px ... pt-28=112px ... pt-40=160px
    '[class*="pt-10"],[class*="pt-12"],[class*="pt-14"],[class*="pt-16"],[class*="pt-20"],[class*="pt-24"],[class*="pt-28"],[class*="pt-32"],[class*="pt-36"],[class*="pt-40"],[class*="pt-44"],[class*="pt-48"],[class*="pt-56"],[class*="pt-64"],[class*="pt-72"],[class*="pt-80"],[class*="pt-96"] { padding-top: 8px !important; }',
    '[class*="pb-10"],[class*="pb-12"],[class*="pb-16"],[class*="pb-20"],[class*="pb-24"],[class*="pb-28"],[class*="pb-32"],[class*="pb-40"] { padding-bottom: 8px !important; }',
    '[class*="py-10"],[class*="py-12"],[class*="py-14"],[class*="py-16"],[class*="py-20"],[class*="py-24"],[class*="py-28"],[class*="py-32"],[class*="py-36"],[class*="py-40"],[class*="py-44"],[class*="py-48"],[class*="py-56"],[class*="py-64"] { padding-top: 8px !important; padding-bottom: 8px !important; }',
    '[class*="mt-8"],[class*="mt-10"],[class*="mt-12"],[class*="mt-14"],[class*="mt-16"],[class*="mt-20"],[class*="mt-24"],[class*="mt-28"],[class*="mt-32"],[class*="mt-36"],[class*="mt-40"],[class*="mt-44"],[class*="mt-48"],[class*="mt-56"],[class*="mt-64"],[class*="mt-72"],[class*="mt-80"],[class*="mt-96"] { margin-top: 8px !important; }',
    '[class*="mb-8"],[class*="mb-10"],[class*="mb-12"],[class*="mb-14"],[class*="mb-16"],[class*="mb-20"],[class*="mb-24"],[class*="mb-28"],[class*="mb-32"],[class*="mb-36"],[class*="mb-40"],[class*="mb-44"],[class*="mb-48"],[class*="mb-56"],[class*="mb-64"] { margin-bottom: 8px !important; }',
    '[class*="my-8"],[class*="my-10"],[class*="my-12"],[class*="my-14"],[class*="my-16"],[class*="my-20"],[class*="my-24"],[class*="my-28"],[class*="my-32"] { margin-top: 4px !important; margin-bottom: 4px !important; }',
    // Arbitrary Tailwind values: pt-[calc(...)], py-[XXrem], mt-[XXpx], etc.
    '[class*="pt-["] { padding-top: 16px !important; }',
    '[class*="pb-["] { padding-bottom: 16px !important; }',
    '[class*="py-["] { padding-top: 8px !important; padding-bottom: 8px !important; }',
    '[class*="mt-["] { margin-top: 8px !important; }',
    '[class*="mb-["] { margin-bottom: 8px !important; }',
    '[class*="my-["] { margin-top: 4px !important; margin-bottom: 4px !important; }',
    // Prose (typography) spacing compression
    '.prose { margin-top: 8px !important; margin-bottom: 8px !important; }',
    '.prose > * + * { margin-top: 8px !important; }',
    '.prose h2, .prose h3, .prose h4 { margin-top: 16px !important; margin-bottom: 8px !important; }',
    '.prose pre { margin-top: 8px !important; margin-bottom: 8px !important; }',
    '.prose ul, .prose ol { margin-top: 4px !important; margin-bottom: 4px !important; }',
    '.prose p { margin-top: 4px !important; margin-bottom: 4px !important; }',
    // Gap compression
    '.gap-12 { gap: 16px !important; }',
    '.gap-10 { gap: 12px !important; }',
    '.gap-8 { gap: 8px !important; }',
    // Section divider spacing
    '[class*="gap-y-8"],[class*="gap-y-10"],[class*="gap-y-12"],[class*="gap-y-16"],[class*="gap-y-20"] { gap-top: 8px !important; gap-bottom: 8px !important; }',
  ].join('');
  document.head.appendChild(bgStyle);

  // 12. Cream/light yellow background → pure white (preserve code blocks/callouts)
  document.querySelectorAll('*').forEach(function(el) {
    var bg = window.getComputedStyle(el).backgroundColor;
    var tag = el.tagName;
    var cls = el.getAttribute('class') || '';
    // Skip content elements that should keep their backgrounds
    if (tag === 'CODE' || tag === 'PRE' ||
        cls.indexOf('callout') >= 0 || cls.indexOf('prose') >= 0 ||
        cls.indexOf('code') >= 0 || cls.indexOf('block') >= 0 ||
        tag === 'TABLE' || tag === 'TD' || tag === 'TH' || tag === 'TR' ||
        tag === 'THEAD' || tag === 'TBODY') {
      return;
    }
    // Match cream/light colors - also handle accordion/foldable sections
    if (bg === 'rgb(253, 253, 247)' || bg === 'rgb(250, 250, 250)' || bg === 'rgb(249, 250, 251)' ||
        bg === 'rgb(248, 249, 250)' || bg === 'rgb(245, 245, 245)') {
      el.style.setProperty('background-color', '#FFFFFF', 'important');
    }
  });

  // Also fix accordion/details cream backgrounds
  document.querySelectorAll('details, [class*="accordion"]').forEach(function(el) {
    var bg = window.getComputedStyle(el).backgroundColor;
    if (bg === 'rgb(253, 253, 247)' || bg === 'rgb(250, 250, 250)' || bg === 'rgb(249, 250, 251)' ||
        bg === 'rgb(248, 249, 250)' || bg === 'rgb(245, 245, 245)') {
      el.style.setProperty('background-color', '#FFFFFF', 'important');
    }
  });

  // 13. Remove height constraints
  document.body.style.setProperty('height', 'auto', 'important');
  document.body.style.setProperty('min-height', 'auto', 'important');
  document.documentElement.style.setProperty('height', 'auto', 'important');
  document.documentElement.style.setProperty('min-height', 'auto', 'important');
}
"""


# ============================================================
# Cover page HTML
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


def generate_page_pdf(browser, context, url, output_path):
    """Generate a single page PDF with DOM manipulation."""
    page = context.new_page()
    try:
        try:
            page.goto(url, wait_until='networkidle', timeout=60000)
        except Exception:
            pass  # Continue even on timeout
        page.wait_for_timeout(3000)

        # Check for 404
        is_404 = page.evaluate('''() => {
            var h1 = document.querySelector('h1');
            return h1 && h1.textContent && (h1.textContent.includes('404') || h1.textContent.includes('Not Found'));
        }''')
        if is_404:
            page.close()
            return False

        # Apply DOM manipulation
        page.evaluate(DOM_MANIPULATE_JS)

        # Wait for images
        page.wait_for_timeout(3000)

        # Generate PDF
        page.pdf(
            path=output_path,
            format='A4',
            print_background=True,
            margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'},
        )

        page.close()
        return True
    except Exception as e:
        print(f'    Error: {e}')
        try:
            page.close()
        except Exception:
            pass
        return False


def main():
    print('Step 2: Generating individual PDFs')
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

    # Generate page PDFs
    print('  Generating page PDFs...')
    print()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        )

        success = 0
        skipped = 0
        failed = 0

        for idx, page_data in enumerate(pages, 1):
            title = page_data['title']
            href = page_data['href']
            url = f'{ORIGIN}{href}'
            filename = url_to_filename(url) + '.pdf'
            output_path = pdfs_dir / filename

            if output_path.exists() and output_path.stat().st_size > 0:
                skipped += 1
                print(f'    [{idx:3d}/{total}] ⏭ Skip: {title}')
                continue

            ok = generate_page_pdf(browser, context, url, str(output_path))

            if ok:
                size_kb = output_path.stat().st_size / 1024 if output_path.exists() else 0
                print(f'    [{idx:3d}/{total}] {title:<50s} {size_kb:>8.1f} KB')
                success += 1
            else:
                print(f'    [{idx:3d}/{total}] {title:<50s} FAILED')
                failed += 1

        context.close()
        browser.close()

    print()
    print(f'  Summary: {success} generated, {skipped} skipped, {failed} failed')
    print(f'  Output directory: {pdfs_dir}/')


if __name__ == '__main__':
    main()
