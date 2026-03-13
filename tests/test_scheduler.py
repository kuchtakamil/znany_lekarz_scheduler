from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from znany_lekarz_scheduler.config.models import (
    AppConfig,
    BrowserConfig,
    DoctorConfig,
    NotificationConfig,
    ScheduleConfig,
)
from znany_lekarz_scheduler.monitor.scheduler import MonitorScheduler
from znany_lekarz_scheduler.monitor.session import SessionManager
from znany_lekarz_scheduler.monitor.state_manager import StateManager
from znany_lekarz_scheduler.notifier.apprise_notifier import AppriseNotifier
from znany_lekarz_scheduler.scraper.slots_parser import AppointmentSlot


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_config(
    active_start: time = time(7, 0),
    active_end: time = time(22, 30),
    active_days: list[str] | None = None,
    interval_minutes: int = 45,
    jitter_percent: int = 25,
    doctors: list[DoctorConfig] | None = None,
) -> AppConfig:
    if active_days is None:
        active_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    if doctors is None:
        doctors = [DoctorConfig(name="Dr Test", url="https://example.pl/doc")]
    return AppConfig(
        doctors=doctors,
        schedule=ScheduleConfig(
            check_interval_minutes=interval_minutes,
            active_hours_start=active_start,
            active_hours_end=active_end,
            active_days=active_days,
            jitter_percent=jitter_percent,
        ),
        browser=BrowserConfig(),
        notifications=NotificationConfig(),
        login_email="a@b.com",
        login_password="pass",
    )


def _make_slot(url: str = "https://example.pl/doc") -> AppointmentSlot:
    dt = datetime(2026, 3, 16, 9, 0)
    return AppointmentSlot(
        doctor_name="Dr Test",
        doctor_url=url,
        dt=dt,
        slot_id=AppointmentSlot.make_id(url, dt),
        location=None,
    )


def _build_scheduler(
    config: AppConfig | None = None,
    state_manager: StateManager | None = None,
    tmp_path: Path | None = None,
) -> MonitorScheduler:
    cfg = config or _make_config()

    if state_manager is None:
        sm = StateManager(tmp_path / "state.json" if tmp_path else Path("/nonexistent/state.json"))
    else:
        sm = state_manager

    page = MagicMock()
    session_manager = MagicMock(spec=SessionManager)
    session_manager.refresh_if_needed = AsyncMock(return_value=True)

    notifier = MagicMock(spec=AppriseNotifier)
    notifier.send_new_slots = AsyncMock()

    sched = MonitorScheduler(cfg, page, session_manager, sm, notifier)
    # Replace APScheduler so tests don't actually start background threads
    sched._scheduler = MagicMock()
    sched._scheduler.running = False
    # Bypass rate limiter delays
    sched._rate_limiter.acquire = AsyncMock()

    return sched


# ── _is_within_active_hours ───────────────────────────────────────────────────

class TestIsWithinActiveHours:
    def _sched(self, **kw) -> MonitorScheduler:
        return _build_scheduler(config=_make_config(**kw))

    def _patch_now(self, sched: MonitorScheduler, dt: datetime):
        return patch(
            "znany_lekarz_scheduler.monitor.scheduler.datetime",
            **{"now.return_value": dt, "side_effect": lambda *a, **kw: datetime(*a, **kw)},
        )

    def test_midday_weekday_is_active(self) -> None:
        sched = self._sched()
        with patch("znany_lekarz_scheduler.monitor.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 16, 12, 0)  # Mon noon
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert sched._is_within_active_hours()

    def test_midnight_is_inactive(self) -> None:
        sched = self._sched()
        with patch("znany_lekarz_scheduler.monitor.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 16, 0, 30)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert not sched._is_within_active_hours()

    def test_before_active_start_is_inactive(self) -> None:
        sched = self._sched(active_start=time(8, 0))
        with patch("znany_lekarz_scheduler.monitor.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 16, 7, 59)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert not sched._is_within_active_hours()

    def test_after_active_end_is_inactive(self) -> None:
        sched = self._sched(active_end=time(22, 30))
        with patch("znany_lekarz_scheduler.monitor.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 16, 23, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert not sched._is_within_active_hours()

    def test_excluded_day_is_inactive(self) -> None:
        sched = self._sched(active_days=["mon", "tue", "wed", "thu", "fri"])
        with patch("znany_lekarz_scheduler.monitor.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 14, 12, 0)  # Saturday
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert not sched._is_within_active_hours()


# ── Interval helpers ──────────────────────────────────────────────────────────

class TestIntervalHelpers:
    def test_interval_seconds(self) -> None:
        sched = _build_scheduler(config=_make_config(interval_minutes=45))
        assert sched._interval_seconds() == 45 * 60

    def test_jitter_seconds(self) -> None:
        sched = _build_scheduler(config=_make_config(interval_minutes=60, jitter_percent=25))
        assert sched._jitter_seconds() == 60 * 60 * 25 // 100


# ── Bootstrap logic ───────────────────────────────────────────────────────────

class TestBootstrap:
    def test_bootstrap_set_when_no_state_file(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path / "missing.json")
        sched = _build_scheduler(state_manager=sm)
        assert len(sched._bootstrap_doctors) == 1

    def test_bootstrap_empty_when_state_file_exists(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("[]", encoding="utf-8")
        sm = StateManager(state_file)
        sched = _build_scheduler(state_manager=sm)
        assert len(sched._bootstrap_doctors) == 0


# ── _check_doctor ─────────────────────────────────────────────────────────────

class TestCheckDoctor:
    def _active_sched(self, tmp_path: Path | None = None, **kw) -> MonitorScheduler:
        sched = _build_scheduler(tmp_path=tmp_path, **kw)
        # Patch active-hours check to always return True
        sched._is_within_active_hours = MagicMock(return_value=True)
        return sched

    async def test_notifies_new_slots_when_state_exists(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("[]", encoding="utf-8")  # file exists → no bootstrap
        sm = StateManager(state_file)
        sched = self._active_sched(state_manager=sm)
        doctor = _make_config().doctors[0]
        slot = _make_slot()
        sched._scraper.get_available_slots = AsyncMock(return_value=[slot])

        await sched._check_doctor(doctor)

        sched._notifier.send_new_slots.assert_awaited_once()

    async def test_no_notification_on_bootstrap_run(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path / "missing.json")  # no state file
        sched = self._active_sched(state_manager=sm)
        doctor = _make_config().doctors[0]
        slot = _make_slot()
        sched._scraper.get_available_slots = AsyncMock(return_value=[slot])

        await sched._check_doctor(doctor)

        sched._notifier.send_new_slots.assert_not_awaited()

    async def test_bootstrap_doctor_removed_after_first_check(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path / "missing.json")
        sched = self._active_sched(state_manager=sm)
        doctor = _make_config().doctors[0]
        sched._scraper.get_available_slots = AsyncMock(return_value=[])

        await sched._check_doctor(doctor)

        assert doctor.url not in sched._bootstrap_doctors

    async def test_state_saved_after_check(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("[]", encoding="utf-8")
        sm = StateManager(state_file)
        sched = self._active_sched(state_manager=sm)
        doctor = _make_config().doctors[0]
        slot = _make_slot()
        sched._scraper.get_available_slots = AsyncMock(return_value=[slot])

        await sched._check_doctor(doctor)

        saved = sm.load_known_slots()
        assert slot.slot_id in saved

    async def test_skips_outside_active_hours(self, tmp_path: Path) -> None:
        sched = _build_scheduler(tmp_path=tmp_path)
        sched._is_within_active_hours = MagicMock(return_value=False)
        sched._scraper.get_available_slots = AsyncMock()
        doctor = _make_config().doctors[0]

        await sched._check_doctor(doctor)

        sched._scraper.get_available_slots.assert_not_awaited()

    async def test_skips_when_session_refresh_fails(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("[]", encoding="utf-8")
        sm = StateManager(state_file)
        sched = self._active_sched(state_manager=sm)
        sched._session_manager.refresh_if_needed = AsyncMock(return_value=False)
        sched._scraper.get_available_slots = AsyncMock()
        doctor = _make_config().doctors[0]

        await sched._check_doctor(doctor)

        sched._scraper.get_available_slots.assert_not_awaited()

    async def test_handles_scrape_error_gracefully(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("[]", encoding="utf-8")
        sm = StateManager(state_file)
        sched = self._active_sched(state_manager=sm)
        sched._scraper.get_available_slots = AsyncMock(side_effect=Exception("network error"))
        # Bypass retry sleeps
        sched._scrape_with_retry = AsyncMock(side_effect=Exception("network error"))
        doctor = _make_config().doctors[0]

        await sched._check_doctor(doctor)  # must not raise

        sched._notifier.send_new_slots.assert_not_awaited()

    async def test_no_duplicate_notification_for_known_slots(self, tmp_path: Path) -> None:
        slot = _make_slot()
        state_file = tmp_path / "state.json"
        import json
        state_file.write_text(json.dumps([slot.slot_id]), encoding="utf-8")
        sm = StateManager(state_file)
        sched = self._active_sched(state_manager=sm)
        sched._scraper.get_available_slots = AsyncMock(return_value=[slot])
        doctor = _make_config().doctors[0]

        await sched._check_doctor(doctor)

        sched._notifier.send_new_slots.assert_not_awaited()
