"""Chromium-based PDF rendering for the browser-rendered research report."""

import asyncio

from playwright.async_api import Browser, Playwright, Route, async_playwright

_browser: Browser | None = None
_playwright: Playwright | None = None
_browser_lock = asyncio.Lock()
_export_slots = asyncio.Semaphore(2)


async def _get_browser() -> Browser:
    global _browser, _playwright
    async with _browser_lock:
        if _browser is None or not _browser.is_connected():
            _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch()
    return _browser


async def _guard_request(route: Route) -> None:
    """Keep browser-rendered markup from making network or local-file requests."""
    if route.request.url.startswith(("data:", "blob:", "about:")):
        await route.continue_()
    else:
        await route.abort()


async def render_report_pdf(html: str) -> bytes:
    """Render a self-contained report document using Chromium's print engine."""
    async with _export_slots:
        browser = await _get_browser()
        context = await browser.new_context(
            accept_downloads=False,
            java_script_enabled=False,
            service_workers="block",
            viewport={"width": 1100, "height": 900},
        )
        try:
            page = await context.new_page()
            await page.route("**/*", _guard_request)
            await page.set_content(html, wait_until="load", timeout=20_000)
            await page.emulate_media(media="print")
            await page.evaluate(
                """async () => {
                    if (document.fonts) await document.fonts.ready;
                    await Promise.all(
                        Array.from(document.images, image => image.decode().catch(() => undefined))
                    );
                }"""
            )
            return await page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                display_header_footer=True,
                header_template="<div></div>",
                footer_template=(
                    '<div style="width:100%;padding:0 14mm;text-align:right;'
                    'font:9px Arial,sans-serif;color:#667085">'
                    '<span class="pageNumber"></span> / '
                    '<span class="totalPages"></span></div>'
                ),
                margin={
                    "top": "14mm",
                    "right": "14mm",
                    "bottom": "18mm",
                    "left": "14mm",
                },
            )
        finally:
            await context.close()


async def close_pdf_browser() -> None:
    """Close Chromium during application shutdown."""
    global _browser, _playwright
    async with _browser_lock:
        if _browser is not None:
            await _browser.close()
            _browser = None
        if _playwright is not None:
            await _playwright.stop()
            _playwright = None
