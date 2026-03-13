from __future__ import annotations

from datetime import datetime

import pytest

from znany_lekarz_scheduler.notifier.formatter import format_new_slots, format_test_message
from znany_lekarz_scheduler.scraper.slots_parser import AppointmentSlot


def _slot(hour: int, minute: int = 0, url: str = "https://example.pl/doc", name: str = "Dr Test", location: str | None = "Krakow") -> AppointmentSlot:
    dt = datetime(2026, 3, 16, hour, minute)  # Monday
    return AppointmentSlot(
        doctor_name=name,
        doctor_url=url,
        dt=dt,
        slot_id=AppointmentSlot.make_id(url, dt),
        location=location,
    )


class TestFormatNewSlots:
    def test_single_slot_title(self) -> None:
        title, _ = format_new_slots([_slot(8, 30)])
        assert "1" in title
        assert "Nowe terminy" in title

    def test_single_slot_body_contains_time(self) -> None:
        _, body = format_new_slots([_slot(8, 30)])
        assert "08:30" in body

    def test_single_slot_body_contains_doctor_name(self) -> None:
        _, body = format_new_slots([_slot(8)])
        assert "Dr Test" in body

    def test_single_slot_body_contains_location(self) -> None:
        _, body = format_new_slots([_slot(8)])
        assert "Krakow" in body

    def test_no_location_omitted(self) -> None:
        _, body = format_new_slots([_slot(8, location=None)])
        assert "None" not in body

    def test_multiple_slots_same_doctor(self) -> None:
        slots = [_slot(8), _slot(9), _slot(11)]
        title, body = format_new_slots(slots)
        assert "3" in title
        assert "08:00" in body
        assert "09:00" in body
        assert "11:00" in body

    def test_slots_sorted_by_time(self) -> None:
        slots = [_slot(11), _slot(8), _slot(9, 30)]
        _, body = format_new_slots(slots)
        pos_8 = body.index("08:00")
        pos_9 = body.index("09:30")
        pos_11 = body.index("11:00")
        assert pos_8 < pos_9 < pos_11

    def test_multiple_doctors_title_mentions_count(self) -> None:
        slots = [
            _slot(8, url="https://example.pl/doc1", name="Dr A"),
            _slot(9, url="https://example.pl/doc2", name="Dr B"),
        ]
        title, _ = format_new_slots(slots)
        assert "2" in title  # 2 lekarzy

    def test_multiple_doctors_body_contains_both_names(self) -> None:
        slots = [
            _slot(8, url="https://example.pl/doc1", name="Dr A"),
            _slot(9, url="https://example.pl/doc2", name="Dr B"),
        ]
        _, body = format_new_slots(slots)
        assert "Dr A" in body
        assert "Dr B" in body

    def test_body_contains_url(self) -> None:
        _, body = format_new_slots([_slot(8)])
        assert "https://example.pl/doc" in body

    def test_weekday_abbreviation_monday(self) -> None:
        # 2026-03-16 is a Monday
        _, body = format_new_slots([_slot(8)])
        assert "Pon" in body


class TestFormatTestMessage:
    def test_returns_title_and_body(self) -> None:
        title, body = format_test_message()
        assert title
        assert body
