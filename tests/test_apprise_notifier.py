from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from znany_lekarz_scheduler.config.models import NotificationConfig
from znany_lekarz_scheduler.notifier.apprise_notifier import AppriseNotifier
from znany_lekarz_scheduler.scraper.slots_parser import AppointmentSlot


def _config(cooldown_minutes: int = 120, urls: list[str] | None = None) -> NotificationConfig:
    return NotificationConfig(apprise_urls=urls or ["tgram://faketoken/123"], cooldown_minutes=cooldown_minutes)


def _slot(hour: int, url: str = "https://example.pl/doc", name: str = "Dr Test") -> AppointmentSlot:
    dt = datetime(2026, 3, 16, hour, 0)
    return AppointmentSlot(
        doctor_name=name,
        doctor_url=url,
        dt=dt,
        slot_id=AppointmentSlot.make_id(url, dt),
        location="Krakow",
    )


def _make_notifier(cooldown_minutes: int = 120) -> tuple[AppriseNotifier, AsyncMock]:
    notifier = AppriseNotifier(_config(cooldown_minutes=cooldown_minutes))
    mock_notify = AsyncMock(return_value=True)
    notifier._apprise.async_notify = mock_notify
    return notifier, mock_notify


class TestSendNewSlots:
    async def test_sends_notification_for_new_slots(self) -> None:
        notifier, mock_notify = _make_notifier()
        await notifier.send_new_slots([_slot(8), _slot(9)])
        mock_notify.assert_awaited_once()

    async def test_empty_slots_does_not_notify(self) -> None:
        notifier, mock_notify = _make_notifier()
        await notifier.send_new_slots([])
        mock_notify.assert_not_awaited()

    async def test_cooldown_prevents_second_notification(self) -> None:
        notifier, mock_notify = _make_notifier(cooldown_minutes=120)
        await notifier.send_new_slots([_slot(8)])
        await notifier.send_new_slots([_slot(9)])  # same doctor, within cooldown
        assert mock_notify.await_count == 1

    async def test_cooldown_expired_allows_notification(self) -> None:
        notifier, mock_notify = _make_notifier(cooldown_minutes=120)
        url = "https://example.pl/doc"
        # Manually set last_notified to 3 hours ago
        notifier._last_notified[url] = datetime.now() - timedelta(hours=3)
        await notifier.send_new_slots([_slot(8, url=url)])
        mock_notify.assert_awaited_once()

    async def test_different_doctors_notified_independently(self) -> None:
        notifier, mock_notify = _make_notifier()
        url_a = "https://example.pl/doc_a"
        url_b = "https://example.pl/doc_b"
        # Notify doc_a first, putting it on cooldown
        await notifier.send_new_slots([_slot(8, url=url_a, name="Dr A")])
        # doc_b should still get notified
        await notifier.send_new_slots([_slot(9, url=url_b, name="Dr B")])
        assert mock_notify.await_count == 2

    async def test_notified_doctor_recorded_after_send(self) -> None:
        notifier, _ = _make_notifier()
        url = "https://example.pl/doc"
        await notifier.send_new_slots([_slot(8, url=url)])
        assert url in notifier._last_notified

    async def test_failed_send_does_not_update_cooldown(self) -> None:
        notifier, mock_notify = _make_notifier()
        mock_notify.return_value = False
        url = "https://example.pl/doc"
        await notifier.send_new_slots([_slot(8, url=url)])
        assert url not in notifier._last_notified


class TestSendTest:
    async def test_send_test_calls_notify(self) -> None:
        notifier, mock_notify = _make_notifier()
        await notifier.send_test()
        mock_notify.assert_awaited_once()

    async def test_send_test_title_not_empty(self) -> None:
        notifier, mock_notify = _make_notifier()
        await notifier.send_test()
        call_kwargs = mock_notify.call_args.kwargs
        assert call_kwargs["title"]
        assert call_kwargs["body"]


class TestCooldown:
    def test_no_cooldown_when_never_notified(self) -> None:
        notifier = AppriseNotifier(_config())
        assert not notifier._is_on_cooldown("https://example.pl/doc")

    def test_on_cooldown_immediately_after_notify(self) -> None:
        notifier = AppriseNotifier(_config(cooldown_minutes=120))
        url = "https://example.pl/doc"
        notifier._last_notified[url] = datetime.now()
        assert notifier._is_on_cooldown(url)

    def test_not_on_cooldown_after_expiry(self) -> None:
        notifier = AppriseNotifier(_config(cooldown_minutes=120))
        url = "https://example.pl/doc"
        notifier._last_notified[url] = datetime.now() - timedelta(hours=3)
        assert not notifier._is_on_cooldown(url)
