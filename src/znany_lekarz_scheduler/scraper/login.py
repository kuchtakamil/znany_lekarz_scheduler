from __future__ import annotations

import structlog
from playwright.async_api import Page

from ..browser.human_behavior import HumanBehaviorSimulator
from ..utils.delays import post_login_delay

log = structlog.get_logger(__name__)

LOGIN_URL = "https://l.znany lekarz.pl/"
EMAIL_SELECTOR = "#username"        # input[name="_username"]
PASSWORD_SELECTOR = "#password"     # input[name="_password"]
SUBMIT_SELECTOR = 'button[data-test-id="btn-login"]'


class LoginError(Exception):
    pass


class LoginManager:
    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._human = HumanBehaviorSimulator()

    async def login(self, page: Page) -> None:
        """Navigate to login page, fill form, submit, verify success."""
        log.info("login_start", url=LOGIN_URL)

        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        await self._human.random_delay(1500, 3000)

        # Wait for FriendlyCaptcha to complete (proof-of-work, no user action needed)
        await page.wait_for_selector(EMAIL_SELECTOR, timeout=10000)

        # Fill email
        await self._human.type_slowly(page, EMAIL_SELECTOR, self._email)
        await self._human.random_delay(400, 900)

        # Fill password
        await self._human.type_slowly(page, PASSWORD_SELECTOR, self._password)
        await self._human.random_delay(600, 1400)

        # Wait a moment for captcha proof-of-work to finish before submitting
        await self._human.random_delay(1500, 3000)

        # Click submit
        await self._human.random_pause_before_click()
        await page.locator(SUBMIT_SELECTOR).click()

        # Wait for redirect after login
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
        await post_login_delay()

        if not await self.is_logged_in(page):
            current_url = page.url
            raise LoginError(f"Login failed: still on login page or no session indicator (url={current_url})")

        log.info("login_success", redirect_url=page.url)

    async def is_logged_in(self, page: Page) -> bool:
        """Check if we're no longer on the login page (i.e., redirect happened)."""
        try:
            return LOGIN_URL not in page.url and "login" not in page.url
        except Exception:
            return False
