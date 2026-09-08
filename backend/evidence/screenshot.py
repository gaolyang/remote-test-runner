from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class ScreenshotError(RuntimeError):
    pass


class ScreenshotService:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self._lock = asyncio.Lock()

    async def capture_step(self, session_id: str, destination: Path) -> Path:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ScreenshotError("Playwright is not installed") from exc

        destination.parent.mkdir(parents=True, exist_ok=True)
        url = f"{self.base_url}/?{urlencode({'session_id': session_id, 'capture': '1'})}"
        async with self._lock:
            try:
                async with async_playwright() as playwright:
                    browser_channel = os.getenv("RTR_BROWSER_CHANNEL")
                    if browser_channel:
                        browser = await playwright.chromium.launch(
                            headless=True, channel=browser_channel
                        )
                    else:
                        try:
                            browser = await playwright.chromium.launch(headless=True)
                        except Exception as chromium_error:
                            logger.warning(
                                "Bundled Playwright Chromium is unavailable; trying installed Microsoft Edge: %s",
                                chromium_error,
                            )
                            try:
                                browser = await playwright.chromium.launch(
                                    headless=True, channel="msedge"
                                )
                            except Exception as edge_error:
                                raise ScreenshotError(
                                    "No usable browser. Run 'python -m playwright install chromium' "
                                    "or set RTR_BROWSER_CHANNEL to an installed Playwright browser channel. "
                                    f"Chromium: {chromium_error}; Edge: {edge_error}"
                                ) from edge_error
                    page = await browser.new_page(viewport={"width": 1280, "height": 900})
                    await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    await page.locator("#evidence-area").wait_for(state="visible", timeout=20_000)
                    await page.wait_for_function(
                        "document.body.dataset.evidenceReady === 'true'", timeout=20_000
                    )
                    await page.locator("#evidence-area").screenshot(path=str(destination))
                    await browser.close()
            except Exception as exc:
                logger.exception("Screenshot capture failed")
                raise ScreenshotError(str(exc)) from exc
        return destination
