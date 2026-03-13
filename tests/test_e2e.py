"""End-to-end integration tests.

Exercise the full pipeline (config → scheduler → state → notify) using real
implementations of all components except the browser and notification transport,
which are mocked at their boundaries.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from znany_lekarz_scheduler.config.loader import load_config
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


# ── Helpers ───────────────────────────────────────────────────────────────────

_DOCTOR_URL = "https://www.znanylekarz.pl/jan-kowalski/kardiolog/warszawa"


def _slot(dt: datetime | None = None, url: str = _DOCTOR_URL) -> AppointmentSlot:
    dt = dt or datetime(2026, 3, 20, 9, 0)
    return AppointmentSlot(
        doctor_name="Dr Jan Kowalski",
        doctor_url=url,
        dt=dt,
        slot_id=AppointmentSlot.make_id(url, dt),
        location="Kraków",
    )


def _make_config(tmp_path: Path, doctors: list[DoctorConfig] | None = None) -> AppConfig:
    return AppConfig(
        doctors=doctors or [DoctorConfig(name="Dr Jan Kowalski", url=_DOCTOR_URL)],
        schedule=ScheduleConfig(
            check_interval_minutes=45,
            jitter_percent=0,
        ),
        browser=BrowserConfig(),
        notifications=NotificationConfig(apprise_urls=[], cooldown_minutes=0),
        login_email="test@example.com",
        login_password="secret",
    )


def _build_pipeline(
    tmp_path: Path,
    state_file: Path | None = None,
    doctors: list[DoctorConfig] | None = None,
) -> tuple[MonitorScheduler, MagicMock]:
    """Return (scheduler, notifier_mock) with real StateManager."""
    config = _make_config(tmp_path, doctors=doctors)
    state_path = state_file or tmp_path / "state.json"
    state_manager = StateManager(state_path)

    page = MagicMock()
    session_manager = MagicMock(spec=SessionManager)
    session_manager.refresh_if_needed = AsyncMock(return_value=True)

    notifier = MagicMock(spec=AppriseNotifier)
    notifier.send_new_slots = AsyncMock()

    sched = MonitorScheduler(config, page, session_manager, state_manager, notifier)
    sched._scheduler = MagicMock()
    sched._scheduler.running = False
    sched._rate_limiter.acquire = AsyncMock()
    sched._is_within_active_hours = MagicMock(return_value=True)

    return sched, notifier


# ── Config loading ────────────────────────────────────────────────────────────

class TestConfigLoading:
    def test_loads_toml_and_env(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[schedule]
check_interval_minutes = 30

[browser]
headless = true

[notifications]
apprise_urls = ["tgram://TOKEN/CHAT"]

[[doctors]]
name = "Dr Test"
url = "https://www.znanylekarz.pl/dr-test/kardiolog/warszawa"
""",
            encoding="utf-8",
        )

        with patch.dict(
            os.environ,
            {"ZNANY_LEKARZ_EMAIL": "a@b.com", "ZNANY_LEKARZ_PASSWORD": "pw"},
        ):
            config = load_config(config_file)

        assert config.schedule.check_interval_minutes == 30
        assert len(config.doctors) == 1
        assert config.doctors[0].name == "Dr Test"
        assert config.notifications.apprise_urls == ["tgram://TOKEN/CHAT"]
        assert config.login_email == "a@b.com"

    def test_missing_config_raises(self, tmp_path: Path) -> None:
        with patch.dict(
            os.environ,
            {"ZNANY_LEKARZ_EMAIL": "a@b.com", "ZNANY_LEKARZ_PASSWORD": "pw"},
        ):
            with pytest.raises(FileNotFoundError):
                load_config(tmp_path / "nonexistent.toml")


# ── Full pipeline ─────────────────────────────────────────────────────────────

class TestFullPipeline:
    async def test_new_slot_triggers_notification(self, tmp_path: Path) -> None:
        """First run seeds state; second run detects new slot and notifies."""
        state_file = tmp_path / "state.json"
        state_file.write_text("[]", encoding="utf-8")  # pre-existing state → no bootstrap

        sched, notifier = _build_pipeline(tmp_path, state_file=state_file)
        doctor = sched._config.doctors[0]
        slot = _slot()

        sched._scraper.get_available_slots = AsyncMock(return_value=[slot])
        await sched._check_doctor(doctor)

        notifier.send_new_slots.assert_awaited_once()
        (sent_slots,), _ = notifier.send_new_slots.call_args
        assert sent_slots[0].slot_id == slot.slot_id

    async def test_known_slot_does_not_notify(self, tmp_path: Path) -> None:
        slot = _slot()
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps([slot.slot_id]), encoding="utf-8")

        sched, notifier = _build_pipeline(tmp_path, state_file=state_file)
        doctor = sched._config.doctors[0]
        sched._scraper.get_available_slots = AsyncMock(return_value=[slot])

        await sched._check_doctor(doctor)

        notifier.send_new_slots.assert_not_awaited()

    async def test_state_persists_across_restarts(self, tmp_path: Path) -> None:
        """Slots found in run 1 are still known in run 2."""
        state_file = tmp_path / "state.json"
        state_file.write_text("[]", encoding="utf-8")
        slot = _slot()

        # Run 1: detect new slot, save state
        sched1, _ = _build_pipeline(tmp_path, state_file=state_file)
        sched1._scraper.get_available_slots = AsyncMock(return_value=[slot])
        await sched1._check_doctor(sched1._config.doctors[0])

        # Run 2: same slot is now known → no notification
        sched2, notifier2 = _build_pipeline(tmp_path, state_file=state_file)
        sched2._scraper.get_available_slots = AsyncMock(return_value=[slot])
        await sched2._check_doctor(sched2._config.doctors[0])

        notifier2.send_new_slots.assert_not_awaited()

    async def test_multiple_new_slots_all_notified(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("[]", encoding="utf-8")

        sched, notifier = _build_pipeline(tmp_path, state_file=state_file)
        slots = [
            _slot(datetime(2026, 3, 20, 9, 0)),
            _slot(datetime(2026, 3, 20, 10, 0)),
            _slot(datetime(2026, 3, 20, 11, 0)),
        ]
        sched._scraper.get_available_slots = AsyncMock(return_value=slots)

        await sched._check_doctor(sched._config.doctors[0])

        notifier.send_new_slots.assert_awaited_once()
        (sent_slots,), _ = notifier.send_new_slots.call_args
        assert len(sent_slots) == 3


# ── Bootstrap mode ────────────────────────────────────────────────────────────

class TestBootstrapMode:
    async def test_first_run_seeds_state_without_notifying(self, tmp_path: Path) -> None:
        """When no state file exists, first run saves state but sends no notification."""
        sched, notifier = _build_pipeline(tmp_path)  # state file does not exist
        slot = _slot()
        sched._scraper.get_available_slots = AsyncMock(return_value=[slot])

        await sched._check_doctor(sched._config.doctors[0])

        notifier.send_new_slots.assert_not_awaited()

        # State should be saved
        sm = StateManager(tmp_path / "state.json")
        assert slot.slot_id in sm.load_known_slots()

    async def test_second_run_after_bootstrap_notifies(self, tmp_path: Path) -> None:
        """After bootstrap, a new slot that wasn't in initial state triggers notification."""
        sched, notifier = _build_pipeline(tmp_path)
        slot_initial = _slot(datetime(2026, 3, 20, 9, 0))
        slot_new = _slot(datetime(2026, 3, 20, 10, 0))

        # Bootstrap run — no notification
        sched._scraper.get_available_slots = AsyncMock(return_value=[slot_initial])
        await sched._check_doctor(sched._config.doctors[0])
        notifier.send_new_slots.assert_not_awaited()

        # Second run: state file now exists, new slot appears
        state_file = tmp_path / "state.json"
        sched2, notifier2 = _build_pipeline(tmp_path, state_file=state_file)
        sched2._scraper.get_available_slots = AsyncMock(
            return_value=[slot_initial, slot_new]
        )
        await sched2._check_doctor(sched2._config.doctors[0])

        notifier2.send_new_slots.assert_awaited_once()


# ── Error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:
    async def test_scrape_failure_does_not_crash_and_no_notify(
        self, tmp_path: Path
    ) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("[]", encoding="utf-8")
        sched, notifier = _build_pipeline(tmp_path, state_file=state_file)
        sched._scrape_with_retry = AsyncMock(side_effect=RuntimeError("network error"))

        await sched._check_doctor(sched._config.doctors[0])  # must not raise

        notifier.send_new_slots.assert_not_awaited()

    async def test_session_failure_skips_check(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("[]", encoding="utf-8")
        sched, notifier = _build_pipeline(tmp_path, state_file=state_file)
        sched._session_manager.refresh_if_needed = AsyncMock(return_value=False)
        sched._scraper.get_available_slots = AsyncMock()

        await sched._check_doctor(sched._config.doctors[0])

        sched._scraper.get_available_slots.assert_not_awaited()
        notifier.send_new_slots.assert_not_awaited()


# ── Multi-doctor ──────────────────────────────────────────────────────────────

class TestMultiDoctor:
    async def test_independent_state_per_doctor(self, tmp_path: Path) -> None:
        """New slot for doctor B does not affect state for doctor A."""
        url_a = "https://www.znanylekarz.pl/dr-a/kardiolog/warszawa"
        url_b = "https://www.znanylekarz.pl/dr-b/kardiolog/krakow"
        doctors = [
            DoctorConfig(name="Dr A", url=url_a),
            DoctorConfig(name="Dr B", url=url_b),
        ]
        state_file = tmp_path / "state.json"
        slot_a = _slot(url=url_a)
        state_file.write_text(json.dumps([slot_a.slot_id]), encoding="utf-8")

        sched, notifier = _build_pipeline(tmp_path, state_file=state_file, doctors=doctors)

        slot_b = _slot(url=url_b)

        async def scrape(doctor: DoctorConfig) -> list[AppointmentSlot]:
            return [slot_b] if doctor.url == url_b else [slot_a]

        sched._scraper.get_available_slots = scrape

        await sched._check_doctor(doctors[0])
        await sched._check_doctor(doctors[1])

        # Only doctor B has a new slot
        notifier.send_new_slots.assert_awaited_once()
        (sent,), _ = notifier.send_new_slots.call_args
        assert sent[0].doctor_url == url_b