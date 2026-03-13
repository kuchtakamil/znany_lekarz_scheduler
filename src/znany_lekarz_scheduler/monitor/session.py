from __future__ import annotations

from pathlib import Path

import structlog

from ..browser.manager import BrowserManager
from ..scraper.login import LoginError, LoginManager

log = structlog.get_logger(__name__)

SESSION_PATH = Path("data/cookies/session.json")
MAX_LOGIN_ATTEMPTS = 3


class SessionManager:
    """Manages browser session: load -> validate -> re-login if needed."""

    def __init__(self, browser_manager: BrowserManager, login_manager: LoginManager) -> None:
        self._browser = browser_manager
        self._login = login_manager

    async def ensure_session(self) -> None:
        """Ensure there is a valid authenticated session, logging in if necessary."""
        if SESSION_PATH.exists():
            loaded = await self._browser.load_session(SESSION_PATH)
            if loaded:
                log.info("session_loaded", path=str(SESSION_PATH))
                if await self._browser.is_session_valid():
                    log.info("session_valid")
                    return
                log.info("session_expired")
            else:
                log.warning("session_load_failed", path=str(SESSION_PATH))

        await self._do_login()

    async def refresh_if_needed(self) -> bool:
        """Check session validity and re-login if expired. Returns True if session is valid."""
        if await self._browser.is_session_valid():
            return True
        log.warning("session_invalid_refreshing")
        try:
            await self._do_login()
            return True
        except LoginError:
            log.error("session_refresh_failed")
            return False

    async def _do_login(self) -> None:
        page = await self._browser.get_page()
        last_error: Exception | None = None
        for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
            try:
                log.info("login_attempt", attempt=attempt, max=MAX_LOGIN_ATTEMPTS)
                await self._login.login(page)
                await self._browser.save_session(SESSION_PATH)
                log.info("session_saved", path=str(SESSION_PATH))
                return
            except LoginError as e:
                log.warning("login_failed", attempt=attempt, error=str(e))
                last_error = e
        raise LoginError(f"All {MAX_LOGIN_ATTEMPTS} login attempts failed") from last_error
