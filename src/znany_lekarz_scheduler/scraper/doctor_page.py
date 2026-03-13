from __future__ import annotations

import structlog
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from ..browser.human_behavior import HumanBehaviorSimulator
from ..config.models import DoctorConfig
from ..utils.delays import human_delay, page_load_delay
from .slots_parser import AppointmentSlot, get_current_location, parse_available_slots

log = structlog.get_logger(__name__)

# Selectors
_CALENDAR_SELECTOR = ".dp-calendar"
_AVAILABLE_SLOT_SELECTOR = "button.calendar-slot-available"
_NEXT_BTN_SELECTOR = "button.dp-carousel-nav-next[data-controls='next']:not([disabled])"
_SHOW_MORE_SELECTOR = ".dp-calendar-more button"

# How many additional weeks to check beyond the initially visible one
_MAX_EXTRA_WEEKS = 2


class ScraperError(Exception):
    pass


class DoctorPageScraper:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._human = HumanBehaviorSimulator()

    async def get_available_slots(self, doctor: DoctorConfig) -> list[AppointmentSlot]:
        """Main entry point: navigate to doctor page and return all available slots."""
        await self._navigate_to_doctor(doctor.url)
        await self._wait_for_calendar(doctor.url)
        await self._human.scroll_page_naturally(self._page)

        location = await get_current_location(self._page)
        log.info("doctor_page_loaded", doctor=doctor.name, location=location)

        all_slots: list[AppointmentSlot] = []

        # First pass: expand hidden slots and collect visible week
        await self._expand_hidden_slots()
        slots = await parse_available_slots(self._page, doctor.name, doctor.url, location)
        all_slots.extend(slots)
        log.debug("slots_week_0", doctor=doctor.name, count=len(slots))

        # Paginate through next weeks
        for week in range(1, _MAX_EXTRA_WEEKS + 1):
            advanced = await self._handle_pagination()
            if not advanced:
                log.debug("no_more_weeks", doctor=doctor.name, week=week)
                break
            await self._expand_hidden_slots()
            slots = await parse_available_slots(self._page, doctor.name, doctor.url, location)
            all_slots.extend(slots)
            log.debug("slots_week_n", doctor=doctor.name, week=week, count=len(slots))

        log.info("slots_fetched", doctor=doctor.name, total=len(all_slots))
        return all_slots

    async def _navigate_to_doctor(self, url: str) -> None:
        log.debug("navigating", url=url)
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page_load_delay()

    async def _wait_for_calendar(self, url: str) -> None:
        """Wait for the calendar widget to appear on the page."""
        try:
            await self._page.wait_for_selector(_CALENDAR_SELECTOR, timeout=15_000)
        except PlaywrightTimeoutError as e:
            raise ScraperError(
                f"Calendar widget not found on page: {url}. "
                "The page structure may have changed or booking is unavailable."
            ) from e

    async def _expand_hidden_slots(self) -> None:
        """Click 'Pokaż więcej godzin' if present to reveal all slots for current view."""
        try:
            btn = await self._page.query_selector(_SHOW_MORE_SELECTOR)
            if btn and await btn.is_visible():
                await self._human.random_pause_before_click()
                await btn.click()
                await human_delay(1.0, 0.3)
                log.debug("expanded_hidden_slots")
        except Exception as exc:
            log.debug("expand_hidden_slots_skipped", reason=str(exc))

    async def _handle_pagination(self) -> bool:
        """Click the 'Next' carousel button. Returns True if navigation happened."""
        try:
            btn = await self._page.query_selector(_NEXT_BTN_SELECTOR)
            if btn is None or not await btn.is_visible():
                return False

            await self._human.random_pause_before_click()
            await btn.click()
            await human_delay(2.0, 0.5)
            return True
        except PlaywrightTimeoutError:
            return False
        except Exception as exc:
            log.warning("pagination_error", error=str(exc))
            return False
