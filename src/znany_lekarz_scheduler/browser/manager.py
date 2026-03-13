from __future__ import annotations

import json
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from ..config.models import BrowserConfig
from .anti_detection import apply_stealth_settings, get_random_user_agent


class BrowserManager:
    """Manages a single Playwright browser instance."""

    def __init__(self, config: BrowserConfig) -> None:
        self._config = config
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._user_agent = get_random_user_agent()

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        browser_type = getattr(self._playwright, self._config.browser_type)

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]

        self._browser = await browser_type.launch(
            headless=self._config.headless,
            args=launch_args,
        )

        context_kwargs: dict = {
            "viewport": {
                "width": self._config.viewport_width,
                "height": self._config.viewport_height,
            },
            "user_agent": self._user_agent,
            "locale": self._config.locale,
            "timezone_id": self._config.timezone,
            "extra_http_headers": {
                "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            },
        }

        if self._config.user_data_dir:
            self._context = await browser_type.launch_persistent_context(
                self._config.user_data_dir,
                headless=self._config.headless,
                args=launch_args,
                **context_kwargs,
            )
        else:
            self._context = await self._browser.new_context(**context_kwargs)

        self._page = await self._context.new_page()
        await apply_stealth_settings(self._page)

    async def stop(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def get_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def save_session(self, path: Path) -> None:
        if self._context is None:
            raise RuntimeError("No active browser context.")
        path.parent.mkdir(parents=True, exist_ok=True)
        storage_state = await self._context.storage_state()
        path.write_text(json.dumps(storage_state, indent=2), encoding="utf-8")

    async def load_session(self, path: Path) -> bool:
        if not path.exists():
            return False
        if self._context is None:
            raise RuntimeError("No active browser context.")
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            await self._context.add_cookies(state.get("cookies", []))
            return True
        except Exception:
            return False

    async def is_session_valid(self) -> bool:
        """Check session validity: if SSO redirects away from the login page, we're logged in."""
        page = await self.get_page()
        try:
            await page.goto("https://l.znany lekarz.pl/", wait_until="domcontentloaded", timeout=15000)
            # If redirected away from the SSO login domain, session is valid
            return "l.znany lekarz.pl" not in page.url
        except Exception:
            return False
