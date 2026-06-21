"""
Flight Finder — CloakBrowser Factory
Creates stealth Playwright browser instances with anti-detection patches.
Browsers run headed but off-screen for later handoff to user.
"""

import random
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from .fingerprint import generate_random_fingerprint
from .js_patches import JS_PATCHES


class BrowserFactory:
    """Creates stealth Playwright browser instances with CloakBrowser patches."""

    def __init__(self):
        self._playwright = None

    async def _ensure_playwright(self):
        if self._playwright is None:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            self._playwright = pw
        return self._playwright

    async def create_cloak_browser(
        self,
        proxy: Optional[dict] = None,
        cloak_config: Optional[dict] = None,
    ) -> tuple:
        """
        Create a stealth Playwright/Camoufox browser context.
        Returns (browser, context, page) tuple.

        Browser runs in HEADED mode but off-screen (for handoff later).
        """
        config = cloak_config or {}
        use_camoufox = config.get("engine", "playwright").lower() == "camoufox"

        if use_camoufox:
            try:
                logger.info("[BrowserFactory] Launching stealth Camoufox engine (Firefox)...")
                from camoufox.async_api import AsyncCamoufox

                camoufox_proxy = None
                if proxy:
                    camoufox_proxy = {
                        "server": f"{proxy['protocol']}://{proxy['host']}:{proxy['port']}",
                    }
                    if proxy.get("username"):
                        camoufox_proxy["username"] = proxy["username"]
                    if proxy.get("password"):
                        camoufox_proxy["password"] = proxy["password"]

                # Camoufox manages its own stealth profiles and WebRTC/fonts injections
                browser = AsyncCamoufox(
                    headless=False,
                    proxy=camoufox_proxy,
                )
                await browser.start()
                
                context = await browser.new_context(
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                )
                page = await context.new_page()

                # Hide automated window traces (Firefox off-screen strategy)
                try:
                    # Firefox doesn't support CDP setWindowBounds directly like Chromium,
                    # but we can set the page viewport or trigger custom window dimensions.
                    # Standard practice for headed Firefox off-screen handoff:
                    # We can move it off-screen on Windows using OS commands, or
                    # rely on the window-manager to bring it to center on handoff.
                    pass
                except Exception as e:
                    logger.debug(f"Firefox off-screen adjustment error: {e}")

                logger.info("Camoufox browser created successfully.")
                return browser, context, page

            except Exception as e:
                logger.error(f"Failed to launch Camoufox: {e}. Falling back to default Playwright Chromium.")

        # Default Playwright Chromium Flow
        pw = await self._ensure_playwright()
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-translate",
            "--metrics-recording-only",
            "--mute-audio",
        ]

        browser = await pw.chromium.launch(
            headless=False,
            args=launch_args,
        )

        fingerprint = generate_random_fingerprint()

        context_opts = {
            "viewport": fingerprint["viewport"],
            "user_agent": fingerprint["user_agent"],
            "locale": "en-IN",
            "timezone_id": "Asia/Kolkata",
            "geolocation": fingerprint["geolocation"],
            "permissions": ["geolocation"],
            "screen": {"width": 1920, "height": 1080},
            "color_scheme": "light",
            "has_touch": False,
            "is_mobile": False,
        }

        if proxy:
            context_opts["proxy"] = {
                "server": f"{proxy['protocol']}://{proxy['host']}:{proxy['port']}",
            }
            if proxy.get("username"):
                context_opts["proxy"]["username"] = proxy["username"]
            if proxy.get("password"):
                context_opts["proxy"]["password"] = proxy["password"]

        context = await browser.new_context(**context_opts)

        import json
        init_script = f"window.__FINGERPRINT__ = {json.dumps(fingerprint)};\n" + JS_PATCHES
        await context.add_init_script(init_script)

        try:
            from playwright_stealth import stealth_async
            page = await context.new_page()
            await stealth_async(page)
        except ImportError:
            page = await context.new_page()
            logger.debug("playwright-stealth not available, using built-in patches only")

        try:
            show_browser = config.get("showBrowser", False)
            cdp = await context.new_cdp_session(page)
            window_info = await cdp.send("Browser.getWindowForTarget")
            window_id = window_info.get("windowId", 1)
            
            # Position window on-screen if show_browser is toggled, else hide it off-screen
            left_pos = 320 if show_browser else -10000
            top_pos = 140 if show_browser else -10000
            
            await cdp.send("Browser.setWindowBounds", {
                "windowId": window_id,
                "bounds": {
                    "left": left_pos,
                    "top": top_pos,
                    "width": 1280,
                    "height": 800,
                },
            })
            if show_browser:
                logger.info("[BrowserFactory] Browser launched visibly on-screen as per preferences.")
        except Exception as e:
            logger.debug(f"Could not position browser window: {e}")

        logger.info(
            f"CloakBrowser (Chromium) created | UA: {fingerprint['user_agent'][:50]}... | "
            f"Viewport: {fingerprint['viewport']} | Proxy: {bool(proxy)}"
        )

        return browser, context, page

    async def bring_to_foreground(self, context, page, window_id: int = 1):
        """Move a browser window to the center of the screen."""
        try:
            cdp = await context.new_cdp_session(page)
            await cdp.send("Browser.setWindowBounds", {
                "windowId": window_id,
                "bounds": {
                    "left": 320,
                    "top": 140,
                    "width": 1280,
                    "height": 800,
                    "windowState": "normal",
                },
            })

            # Windows: use pywin32 to bring to front
            if sys.platform == "win32":
                try:
                    import win32gui
                    import win32con

                    def callback(hwnd, _):
                        if win32gui.IsWindowVisible(hwnd):
                            title = win32gui.GetWindowText(hwnd)
                            if "Chromium" in title or "Chrome" in title:
                                win32gui.SetForegroundWindow(hwnd)
                                return False
                        return True

                    win32gui.EnumWindows(callback, None)
                except ImportError:
                    logger.debug("pywin32 not available for foreground focus")

            logger.info("Browser brought to foreground for user handoff")
        except Exception as e:
            logger.error(f"Failed to bring browser to foreground: {e}")

    async def cleanup(self):
        """Cleanup Playwright instance."""
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
