from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from playwright.async_api import Page

from ..config.models import AppConfig, DoctorConfig
from ..monitor.session import SessionManager
from ..monitor.state_manager import StateManager
from ..notifier.apprise_notifier import AppriseNotifier
from ..scraper.doctor_page import DoctorPageScraper
from ..scraper.slots_parser import AppointmentSlot
from ..utils.rate_limiter import RateLimiter

log = structlog.get_logger(__name__)

# Exponential backoff delays between scrape retry attempts
_RETRY_DELAYS = [5, 15, 45]


class MonitorScheduler:
    """Orchestrates periodic doctor-slot checks using APScheduler."""

    def __init__(
        self,
        config: AppConfig,
        page: Page,
        session_manager: SessionManager,
        state_manager: StateManager,
        notifier: AppriseNotifier,
    ) -> None:
        self._config = config
        self._scraper = DoctorPageScraper(page)
        self._session_manager = session_manager
        self._state_manager = state_manager
        self._notifier = notifier
        self._rate_limiter = RateLimiter(max_per_minute=2)
        # Serialise all checks: one Page instance shared across doctors
        self._check_lock = asyncio.Lock()
        self._scheduler = AsyncIOScheduler()
        self._stop_event = asyncio.Event()

        # Bootstrap: if no state file exists yet, seed state without notifying
        self._bootstrap_doctors: set[str] = (
            {d.url for d in config.doctors}
            if not state_manager.has_state()
            else set()
        )

    # ── Active-hours guard ────────────────────────────────────────────────────

    def _is_within_active_hours(self) -> bool:
        """Return True if current time falls inside configured active window."""
        schedule = self._config.schedule
        now = datetime.now()
        # strftime("%a") -> "Mon", "Tue", … lowercase to match config
        day_abbr = now.strftime("%a").lower()
        if day_abbr not in schedule.active_days:
            return False
        t = now.time()
        return schedule.active_hours_start <= t <= schedule.active_hours_end

    # ── Interval helpers ──────────────────────────────────────────────────────

    def _interval_seconds(self) -> int:
        return self._config.schedule.check_interval_minutes * 60

    def _jitter_seconds(self) -> int:
        return int(
            self._interval_seconds() * self._config.schedule.jitter_percent / 100
        )

    # ── Core check logic ──────────────────────────────────────────────────────

    async def _scrape_with_retry(self, doctor: DoctorConfig) -> list[AppointmentSlot]:
        """Try scraping up to len(_RETRY_DELAYS) times with exponential backoff."""
        for i, backoff in enumerate(_RETRY_DELAYS):
            try:
                return await self._scraper.get_available_slots(doctor)
            except Exception as exc:
                if i == len(_RETRY_DELAYS) - 1:
                    raise
                log.warning(
                    "scrape_retry",
                    doctor=doctor.name,
                    attempt=i + 1,
                    backoff_s=backoff,
                    error=str(exc),
                )
                await asyncio.sleep(backoff)
        raise RuntimeError("unreachable")

    async def _check_doctor(self, doctor: DoctorConfig) -> None:
        """Single scheduled job: scrape -> diff -> notify -> save."""
        if not self._is_within_active_hours():
            log.debug("outside_active_hours", doctor=doctor.name)
            return

        async with self._check_lock:
            await self._rate_limiter.acquire()

            if not await self._session_manager.refresh_if_needed():
                log.error("session_refresh_failed_skipping", doctor=doctor.name)
                return

            try:
                slots = await self._scrape_with_retry(doctor)
            except Exception as exc:
                log.error("all_retries_exhausted", doctor=doctor.name, error=str(exc))
                return

            known_ids = self._state_manager.load_known_slots()
            new_slots = self._state_manager.find_new_slots(slots, known_ids)

            is_bootstrap = doctor.url in self._bootstrap_doctors
            if new_slots and not is_bootstrap:
                await self._notifier.send_new_slots(new_slots)
            elif is_bootstrap:
                log.info("bootstrap_no_notify", doctor=doctor.name, slots=len(slots))
                self._bootstrap_doctors.discard(doctor.url)

            current_ids = {s.slot_id for s in slots}
            self._state_manager.save_known_slots(known_ids | current_ids)

            log.info(
                "check_complete",
                doctor=doctor.name,
                current=len(slots),
                new=len(new_slots),
            )

    # ── Scheduler lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Schedule one job per doctor with staggered start times, then start the scheduler."""
        interval_s = self._interval_seconds()
        jitter_s = self._jitter_seconds()
        n = max(len(self._config.doctors), 1)
        # Spread first runs evenly across one interval period
        offset_step = interval_s / n

        for i, doctor in enumerate(self._config.doctors):
            offset_s = offset_step * i
            first_run = datetime.now() + timedelta(seconds=offset_s)
            self._scheduler.add_job(
                self._check_doctor,
                trigger=IntervalTrigger(seconds=interval_s, jitter=jitter_s),
                args=[doctor],
                next_run_time=first_run,
                id=f"check_{i}",
                name=doctor.name,
                misfire_grace_time=300,
                coalesce=True,
                max_instances=1,
            )
            log.info(
                "job_scheduled",
                doctor=doctor.name,
                interval_min=self._config.schedule.check_interval_minutes,
                jitter_pct=self._config.schedule.jitter_percent,
                first_run_in_s=int(offset_s),
            )

        self._scheduler.start()
        log.info("scheduler_started", jobs=len(self._config.doctors))

    def stop(self) -> None:
        """Shutdown APScheduler and signal the wait loop to exit."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._stop_event.set()
        log.info("scheduler_stopped")

    async def wait_until_stopped(self) -> None:
        """Block until stop() is called (e.g. via signal handler)."""
        await self._stop_event.wait()
