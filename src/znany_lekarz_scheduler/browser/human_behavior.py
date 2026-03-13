from __future__ import annotations

import asyncio
import math
import random

from playwright.async_api import Page


class HumanBehaviorSimulator:
    async def random_delay(self, min_ms: int = 500, max_ms: int = 3000) -> None:
        await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

    async def move_mouse_naturally(self, page: Page, target_x: int, target_y: int) -> None:
        """Move mouse along a bezier curve to simulate natural movement."""
        current = await page.evaluate("() => ({ x: window.mouseX || 0, y: window.mouseY || 0 })")
        start_x, start_y = current.get("x", 0), current.get("y", 0)

        # Control points for bezier curve
        cp1_x = start_x + random.uniform(-100, 100)
        cp1_y = start_y + random.uniform(-100, 100)
        cp2_x = target_x + random.uniform(-100, 100)
        cp2_y = target_y + random.uniform(-100, 100)

        steps = random.randint(15, 30)
        for i in range(steps + 1):
            t = i / steps
            # Cubic bezier
            x = int(
                (1 - t) ** 3 * start_x
                + 3 * (1 - t) ** 2 * t * cp1_x
                + 3 * (1 - t) * t ** 2 * cp2_x
                + t ** 3 * target_x
            )
            y = int(
                (1 - t) ** 3 * start_y
                + 3 * (1 - t) ** 2 * t * cp1_y
                + 3 * (1 - t) * t ** 2 * cp2_y
                + t ** 3 * target_y
            )
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.01, 0.03))

    async def scroll_page_naturally(self, page: Page) -> None:
        """Scroll down then back up a bit, like a human reading."""
        viewport_height = await page.evaluate("() => window.innerHeight")
        page_height = await page.evaluate("() => document.body.scrollHeight")

        scroll_target = min(page_height * 0.4, viewport_height * 2)
        current_pos = 0

        while current_pos < scroll_target:
            step = random.randint(80, 200)
            current_pos = min(current_pos + step, scroll_target)
            await page.evaluate(f"window.scrollTo(0, {current_pos})")
            await asyncio.sleep(random.uniform(0.05, 0.15))

        # Slight scroll back
        back = random.randint(50, 150)
        await page.evaluate(f"window.scrollTo(0, {max(0, current_pos - back)})")
        await asyncio.sleep(random.uniform(0.3, 0.7))

    async def type_slowly(self, page: Page, selector: str, text: str) -> None:
        """Type text with random delays between keystrokes."""
        element = page.locator(selector)
        await element.click()
        await asyncio.sleep(random.uniform(0.2, 0.5))
        for char in text:
            await element.press(char)
            await asyncio.sleep(random.uniform(0.05, 0.2))

    async def random_pause_before_click(self) -> None:
        """Human-like pause before clicking (reading/deciding)."""
        await asyncio.sleep(random.uniform(0.3, 1.5))
