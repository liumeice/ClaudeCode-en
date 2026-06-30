from playwright.sync_api import sync_playwright
import os
from pathlib import Path
from PIL import Image

url = 'https://code.claude.com/docs/en/hooks'

with open('step2_generate_pdfs.py', 'r', encoding='utf-8') as f:
    content = f.read()
start = content.find('DOM_MANIPULATE_JS = """') + len('DOM_MANIPULATE_JS = """')
end = content.find('"""', start)
dom_js = content[start:end]

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1280, 'height': 800})
    page = context.new_page()
    
    page.goto(url, wait_until='networkidle', timeout=60000)
    page.wait_for_timeout(3000)
    page.evaluate(dom_js)
    page.wait_for_timeout(3000)
    
    # Get full page height
    page_height = page.evaluate('() => document.documentElement.scrollHeight')
    print(f'Page height: {page_height}px')
    
    # Take full page screenshot
    screenshot_path = 'temp/hooks_fullpage.png'
    page.screenshot(path=screenshot_path, full_page=True, timeout=60000)
    
    page.close()
    browser.close()

print(f'Screenshot saved: {screenshot_path}')
print(f'Screenshot size: {os.path.getsize(screenshot_path) / 1024:.1f} KB')

# Convert screenshot to PDF
from PIL import Image
img = Image.open(screenshot_path)
width, height = img.size
print(f'Image dimensions: {width}x{height}')

# A4 size in pixels at 96 DPI: 794x1123
# Calculate pages needed
a4_width = 794
a4_height = 1123

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io

output_pdf = 'temp/hooks_from_screenshot.pdf'
c = canvas.Canvas(output_pdf, pagesize=A4)
page_w, page_h = A4

# Scale image to fit page width
scale = page_w / width
scaled_height = height * scale

# Calculate how many pages needed
pages_needed = int(scaled_height / page_h) + 1
print(f'Pages needed: {pages_needed}')

for page_num in range(pages_needed):
    if page_num > 0:
        c.showPage()
    
    y_offset = page_num * page_h / scale
    
    # Draw image section
    c.drawImage(
        ImageReader(screenshot_path),
        0, 0,
        width=page_w,
        height=page_h,
        preserveAspectRatio=True,
        anchor='c',
        mask='auto'
    )

c.save()
print(f'PDF saved: {output_pdf}')
print(f'PDF size: {os.path.getsize(output_pdf) / 1024:.1f} KB')

# Check for images in PDF
import fitz
doc = fitz.open(output_pdf)
print(f'PDF pages: {doc.page_count}')
all_imgs = []
for p in doc:
    all_imgs.extend(p.get_images())
print(f'Images in PDF: {len(all_imgs)}')
doc.close()
