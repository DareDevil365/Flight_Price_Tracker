"""
Flight Finder — Human Behavior Simulator
Mimics real human interactions: typing speed variance, bezier mouse movement,
random scrolling, micro-pauses, and occasional typos.
"""

import math
import random
import asyncio

from loguru import logger


class HumanSimulator:
    """Simulates human-like browser interactions to evade bot detection."""

    INTENSITY_CONFIG = {
        "LOW": {"type_mean": 60, "type_std": 15, "typo_rate": 0.0, "pause_mean": 300},
        "MEDIUM": {"type_mean": 100, "type_std": 30, "typo_rate": 0.02, "pause_mean": 500},
        "HIGH": {"type_mean": 140, "type_std": 40, "typo_rate": 0.05, "pause_mean": 800},
    }

    def __init__(self, intensity: str = "MEDIUM"):
        self.config = self.INTENSITY_CONFIG.get(intensity, self.INTENSITY_CONFIG["MEDIUM"])
        self.intensity = intensity
        logger.debug(f"HumanSimulator initialized with {intensity} intensity")

    async def type_text(self, page, selector: str, text: str):
        """Type text with human-like speed variance and occasional typos."""
        await page.click(selector)
        await self.random_delay(200, 500)

        for char in text:
            # Occasional typo (only at MEDIUM/HIGH intensity)
            if random.random() < self.config["typo_rate"]:
                wrong_char = random.choice("abcdefghijklmnopqrstuvwxyz")
                await page.keyboard.type(wrong_char, delay=self._typing_delay())
                await self.random_delay(100, 300)
                await page.keyboard.press("Backspace")
                await self.random_delay(50, 150)

            await page.keyboard.type(char, delay=self._typing_delay())

        # Small pause after finishing typing
        await self.random_delay(100, 300)

    async def click_element(self, page, selector: str):
        """Click with bezier-curve mouse movement."""
        try:
            element = await page.query_selector(selector)
            if not element:
                # Fallback to direct click
                await page.click(selector)
                return

            box = await element.bounding_box()
            if not box:
                await page.click(selector)
                return

            target_x = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
            target_y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)

            await self._bezier_move(page, target_x, target_y)
            await self.random_delay(50, 150)
            await page.mouse.click(target_x, target_y)
        except Exception:
            # Fallback
            await page.click(selector)

    async def scroll_randomly(self, page):
        """Simulate natural reading scroll behavior."""
        scroll_amount = random.randint(100, 400)
        direction = random.choice([1, 1, 1, -1])  # 75% chance scroll down
        await page.mouse.wheel(0, scroll_amount * direction)
        await self.random_delay(500, 1500)

    async def random_delay(self, min_ms: int, max_ms: int):
        """Gaussian-distributed delay (more natural than uniform)."""
        mean = (min_ms + max_ms) / 2
        std = (max_ms - min_ms) / 4
        delay = max(min_ms, min(max_ms, random.gauss(mean, std)))
        await asyncio.sleep(delay / 1000)

    async def think_pause(self):
        """Simulate a human 'thinking' pause (longer delay)."""
        await self.random_delay(
            self.config["pause_mean"],
            self.config["pause_mean"] * 3,
        )

    async def read_page(self, page):
        """Simulate reading a page: scroll, pause, scroll."""
        for _ in range(random.randint(1, 3)):
            await self.scroll_randomly(page)
            await self.random_delay(800, 2000)

    def _typing_delay(self) -> int:
        """Gaussian-distributed typing delay in ms."""
        delay = random.gauss(self.config["type_mean"], self.config["type_std"])
        return max(30, int(delay))

    async def _bezier_move(self, page, target_x: float, target_y: float, steps: int = 20):
        """Move mouse along a bezier curve to target position."""
        start_x = random.uniform(100, 500)
        start_y = random.uniform(100, 500)

        # Random control points for natural curve
        cp1_x = start_x + random.uniform(-100, 100)
        cp1_y = start_y + random.uniform(-100, 100)
        cp2_x = target_x + random.uniform(-50, 50)
        cp2_y = target_y + random.uniform(-50, 50)

        for i in range(steps + 1):
            t = i / steps
            # Cubic bezier formula
            x = (
                (1 - t) ** 3 * start_x
                + 3 * (1 - t) ** 2 * t * cp1_x
                + 3 * (1 - t) * t ** 2 * cp2_x
                + t ** 3 * target_x
            )
            y = (
                (1 - t) ** 3 * start_y
                + 3 * (1 - t) ** 2 * t * cp1_y
                + 3 * (1 - t) * t ** 2 * cp2_y
                + t ** 3 * target_y
            )
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.005, 0.02))
