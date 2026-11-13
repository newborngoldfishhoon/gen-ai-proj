import re

import pytest

from app.services.pdf_export import close_pdf_browser, render_report_pdf


@pytest.mark.asyncio
async def test_chromium_renders_a4_pages_and_preserves_links():
    html = """<!doctype html>
    <html><head><style>
      @page { size: A4; margin: 14mm 14mm 18mm; }
      body { font: 14px Arial, sans-serif; color: #172033; }
      .guide { break-before: page; page-break-before: always; }
    </style></head><body>
      <section><h1>Research Report</h1><p>Readable report content.</p></section>
      <section class="guide"><h1>Kickstart Guide</h1>
        <a href="https://example.com">Open resource</a>
      </section>
    </body></html>"""

    try:
        pdf = await render_report_pdf(html)
    finally:
        await close_pdf_browser()

    assert pdf.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 2
    assert b"/MediaBox" in pdf
    assert b"/URI" in pdf
