from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

import apprise
import structlog

from ..config.models import NotificationConfig
from ..scraper.slots_parser import AppointmentSlot
from .base import BaseNotifier
from .formatter import format_new_slots, format_test_message

log = structlog.get_logger(__name__)


class AppriseNotifier(BaseNotifier):
    """Sends notifications via Apprise with per-doctor cooldown."""

    def __init__(self, config: NotificationConfig) -> None:
        self._config = config
        self._cooldown = timedelta(minutes=config.cooldown_minutes)
        self._last_notified: dict[str, datetime] = {}  # doctor_url -> last sent
        self._apprise = self._build_apprise(config.apprise_urls)

    @staticmethod
    def _build_apprise(urls: list[str]) -> apprise.Apprise:
        a = apprise.Apprise()
        for url in urls:
            a.add(url)
        return a

    def _is_on_cooldown(self, doctor_url: str) -> bool:
        last = self._last_notified.get(doctor_url)
        if last is None:
            return False
        return datetime.now() - last < self._cooldown

    async def send_new_slots(self, slots: list[AppointmentSlot]) -> None:
        if not slots:
            return

        # Filter out doctors that are on cooldown
        eligible: list[AppointmentSlot] = []
        skipped_doctors: set[str] = set()
        for slot in slots:
            if self._is_on_cooldown(slot.doctor_url):
                skipped_doctors.add(slot.doctor_name)
            else:
                eligible.append(slot)

        if skipped_doctors:
            log.debug("cooldown_skipped", doctors=sorted(skipped_doctors))

        if not eligible:
            return

        title, body = format_new_slots(eligible)
        log.info("sending_notification", title=title, slot_count=len(eligible))

        ok = await self._apprise.async_notify(title=title, body=body)
        if ok:
            # Mark all eligible doctors as notified
            now = datetime.now()
            by_doctor: dict[str, None] = {}
            for slot in eligible:
                by_doctor[slot.doctor_url] = None
            for doctor_url in by_doctor:
                self._last_notified[doctor_url] = now
            log.debug("notification_sent", doctors=list(by_doctor.keys()))
        else:
            log.warning("notification_failed", title=title)

    async def send_test(self) -> None:
        title, body = format_test_message()
        log.info("sending_test_notification")
        ok = await self._apprise.async_notify(title=title, body=body)
        if ok:
            log.info("test_notification_sent")
        else:
            log.warning("test_notification_failed")
