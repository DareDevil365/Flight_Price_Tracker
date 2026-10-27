"""Isolated headed Chromium browsers, retained briefly for user checkout handoff."""
import asyncio
from loguru import logger

class BrowserFactory:
    _playwright = None
    _shared_browser = None  # Compatibility with session resource ownership checks.
    _lock = asyncio.Lock()

    async def _ensure_playwright(self):
        async with BrowserFactory._lock:
            if BrowserFactory._playwright is None:
                from playwright.async_api import async_playwright
                BrowserFactory._playwright = await async_playwright().start()
        return BrowserFactory._playwright

    async def create_cloak_browser(self, proxy=None, cloak_config=None):
        config = cloak_config or {}
        pw = await self._ensure_playwright()
        # Retain Chromium's actual platform and user agent. Invented fingerprint fields
        # can contradict its browser version and break site scripts.
        browser = await pw.chromium.launch(headless=False, args=[
            "--disable-blink-features=AutomationControlled", "--mute-audio",
            "--disable-backgrounding-occluded-windows",
        ])
        try:
            options = dict(viewport={"width":1280,"height":800}, locale="en-IN", timezone_id="Asia/Kolkata")
            if proxy:
                options["proxy"] = {"server":f"{proxy['protocol']}://{proxy['host']}:{proxy['port']}"}
                for key in ("username","password"):
                    if proxy.get(key):
                        options["proxy"][key] = proxy[key]
            context = await browser.new_context(**options)
            page = await context.new_page()
            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(page)
            except ImportError:
                logger.debug("Optional Playwright stealth helper unavailable")
            try:
                cdp = await context.new_cdp_session(page)
                window = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
                await cdp.send("Browser.setWindowBounds", {"windowId":window,"bounds":{
                    "left":320 if config.get("showBrowser") else -10000,"top":140,"width":1280,"height":800}})
                await cdp.detach()
            except Exception as exc:
                logger.debug(f"Browser positioning unavailable: {exc}")
            return browser,context,page
        except BaseException:
            await browser.close()
            raise

    async def cleanup(self):
        if BrowserFactory._playwright:
            await BrowserFactory._playwright.stop()
            BrowserFactory._playwright = None
