"""
Modular Tools — Stealth Scraper
Generalized, reusable wrapper for Scrapling + Camoufox with built-in human behavior simulation,
rate-limiting, and free proxy rotation. Not specific to flights.
"""

import asyncio
import random
import time
import math
from loguru import logger

# Try to load Scrapling
try:
    from scrapling.fetchers import AsyncStealthyFetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    logger.warning("Scrapling not installed. Please run: pip install scrapling && scrapling install")
    SCRAPLING_AVAILABLE = False


class HumanSimulator:
    def __init__(self, page=None):
        self.page = page

    def set_page(self, page):
        self.page = page

    async def type_chars(self, element, text: str):
        """Types text with Gaussian-distributed keypress delays and simulated typos."""
        if not element:
            return

        for char in text:
            # 5% chance of typo: types adjacent key then backspaces
            if random.random() < 0.05:
                wrong_char = self._get_adjacent_key(char)
                await element.type(wrong_char)
                await asyncio.sleep(random.gauss(0.25, 0.08))
                await element.press("Backspace")
                await asyncio.sleep(random.gauss(0.15, 0.05))

            await element.type(char)
            # Gaussian delay between keypresses: mean=80ms, sigma=30ms, clamped between 40-200ms
            delay = max(0.04, min(0.20, random.gauss(0.08, 0.03)))
            await asyncio.sleep(delay)

    async def move_and_click(self, element):
        """Moves mouse in a non-linear Bezier curve to the target element and clicks."""
        if not self.page or not element:
            return
            
        try:
            box = await element.bounding_box()
            if not box:
                # Fallback to direct click if bounding box unavailable
                await element.click()
                return

            # Target coordinate slightly offset from center
            target_x = box["x"] + random.uniform(box["width"] * 0.3, box["width"] * 0.7)
            target_y = box["y"] + random.uniform(box["height"] * 0.3, box["height"] * 0.7)

            # Get current mouse position (fallback to 0,0 if not tracked)
            current_x, current_y = 0.0, 0.0
            try:
                pos = await self.page.evaluate("() => ({x: window.mouseX || 0, y: window.mouseY || 0})")
                current_x = float(pos.get("x", 0.0))
                current_y = float(pos.get("y", 0.0))
            except Exception:
                pass

            # Generate bezier path points
            points = self._generate_bezier_path(
                (current_x, current_y), 
                (target_x, target_y), 
                steps=20
            )

            # Move along path
            for px, py in points:
                await self.page.mouse.move(px, py)
                # Keep coordinates in window global for tracking
                await self.page.evaluate(f"window.mouseX = {px}; window.mouseY = {py};")
                await asyncio.sleep(random.gauss(8, 2) / 1000.0) # 8ms average between moves

            await self.page.mouse.click(target_x, target_y)
        except Exception as e:
            logger.debug(f"[HumanSim] Click failed: {e}. Fallback to direct click.")
            await element.click()

    async def read_scroll(self, min_px=50, max_px=200):
        """Scrolls down randomly to simulate a user reading content."""
        if not self.page:
            return
        scroll_amount = random.randint(min_px, max_px)
        await self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        # Gaussian delay: mean=1.5s, sigma=0.4s
        await asyncio.sleep(max(0.3, random.gauss(1.5, 0.4)))

    async def human_pause(self, mean_seconds=1.2, sigma=0.4):
        """Pauses for a realistic human reaction time."""
        await asyncio.sleep(max(0.2, random.gauss(mean_seconds, sigma)))

    def _get_adjacent_key(self, char: str) -> str:
        """Returns a keyboard-adjacent key character for typos."""
        keyboard_map = {
            'q': 'w', 'w': 'er', 'e': 'wsd', 'r': 'edf', 't': 'rfg', 'y': 'tgh', 'u': 'yhj', 'i': 'ujk', 'o': 'ikl', 'p': 'ol',
            'a': 'qws', 's': 'wedx', 'd': 'erfc', 'f': 'rtgv', 'g': 'tyhb', 'h': 'yujn', 'j': 'uikm', 'k': 'ijlm', 'l': 'kop',
            'z': 'asx', 'x': 'zsdc', 'c': 'xdfv', 'v': 'cfgb', 'b': 'vghn', 'n': 'bhjm', 'm': 'njk',
            '1': '2', '2': '13q', '3': '24w', '4': '35e', '5': '46r', '6': '57t', '7': '68y', '8': '79u', '9': '80i', '0': '9o'
        }
        char_lower = char.lower()
        if char_lower in keyboard_map:
            choices = keyboard_map[char_lower]
            selected = random.choice(choices)
            return selected.upper() if char.isupper() else selected
        return 's' # default fallback typo key

    def _generate_bezier_path(self, start: tuple, end: tuple, steps: int) -> list:
        """Generates a cubic Bezier curve path from start to end coordinates."""
        x1, y1 = start
        x2, y2 = end
        
        # Determine two control points
        # Control points are offset randomly in the box between start and end
        cx1 = x1 + (x2 - x1) * random.uniform(0.1, 0.5)
        cy1 = y1 + (y2 - y1) * random.uniform(-0.2, 0.5)
        
        cx2 = x1 + (x2 - x1) * random.uniform(0.5, 0.9)
        cy2 = y1 + (y2 - y1) * random.uniform(0.5, 1.2)

        path = []
        for i in range(steps):
            t = i / float(steps - 1)
            # Cubic Bezier formula
            x = ((1 - t) ** 3 * x1 + 
                 3 * (1 - t) ** 2 * t * cx1 + 
                 3 * (1 - t) * t ** 2 * cx2 + 
                 t ** 3 * x2)
            y = ((1 - t) ** 3 * y1 + 
                 3 * (1 - t) ** 2 * t * cy1 + 
                 3 * (1 - t) * t ** 2 * cy2 + 
                 t ** 3 * y2)
            path.append((x, y))
        return path


class ModularStealthScraper:
    def __init__(self, platform_cooldowns: dict = None, default_cooldown: int = 45):
        self.cooldowns = platform_cooldowns or {}
        self.default_cooldown = default_cooldown
        self._last_request_times = {}

    def get_cooldown_delay(self, platform: str) -> float:
        """Calculates required wait time to enforce rate limits."""
        now = time.time()
        last_time = self._last_request_times.get(platform, 0)
        cooldown = self.cooldowns.get(platform, self.default_cooldown)
        elapsed = now - last_time
        
        if elapsed < cooldown:
            return cooldown - elapsed
        return 0.0

    def record_request(self, platform: str):
        """Logs the timestamp of a request to enforce cooldowns next run."""
        self._last_request_times[platform] = time.time()

    async def launch_fetcher(self, headless=True, proxy_url=None):
        """Launches AsyncStealthyFetcher using Scrapling (Firefox/Camoufox)."""
        if not SCRAPLING_AVAILABLE:
            raise RuntimeError("Scrapling library is not available. Please install it.")

        # Instantiate async fetcher
        # Scrapling applies browser fingerprint spoofing at C++ source level
        fetcher = AsyncStealthyFetcher(
            headless=headless,
            network_idle=True,
            block_images=False,
            block_webrtc=True,
            proxy=proxy_url
        )
        return fetcher
