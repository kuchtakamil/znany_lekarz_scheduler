from __future__ import annotations

from datetime import datetime, date
from unittest.mock import patch

import pytest

from znany_lekarz_scheduler.scraper.slots_parser import (
    AppointmentSlot,
    _parse_aria_label,
)


# ── _parse_aria_label ────────────────────────────────────────────────────────

class TestParseAriaLabel:
    def test_basic_available(self):
        dt = _parse_aria_label("08:30 Pon, 16 Mar")
        assert dt is not None
        assert dt.hour == 8
        assert dt.minute == 30
        assert dt.month == 3
        assert dt.day == 16

    def test_booked_same_format(self):
        dt = _parse_aria_label("08:00 Pon, 16 Mar")
        assert dt is not None
        assert dt.hour == 8
        assert dt.minute == 0

    def test_all_pl_months(self):
        months = [
            ("Sty", 1), ("Lut", 2), ("Mar", 3), ("Kwi", 4),
            ("Maj", 5), ("Cze", 6), ("Lip", 7), ("Sie", 8),
            ("Wrz", 9), ("Paź", 10), ("Lis", 11), ("Gru", 12),
        ]
        for abbr, expected_month in months:
            dt = _parse_aria_label(f"10:00 Pon, 1 {abbr}")
            assert dt is not None, f"Failed for month: {abbr}"
            assert dt.month == expected_month

    def test_paz_without_accent(self):
        dt = _parse_aria_label("10:00 Pon, 5 Paz")
        assert dt is not None
        assert dt.month == 10

    def test_invalid_returns_none(self):
        assert _parse_aria_label("") is None
        assert _parse_aria_label("not a date") is None
        assert _parse_aria_label("10:00 Pon") is None

    def test_future_date_same_year(self):
        # Patch today to a fixed date so test is deterministic
        with patch("znany_lekarz_scheduler.scraper.slots_parser.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 13)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            dt = _parse_aria_label("08:30 Pon, 16 Mar")
        assert dt is not None
        assert dt.year == 2026

    def test_past_date_rolls_to_next_year(self):
        with patch("znany_lekarz_scheduler.scraper.slots_parser.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 13)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            dt = _parse_aria_label("08:30 Pon, 5 Sty")  # Jan 5 is in the past
        assert dt is not None
        assert dt.year == 2027


# ── AppointmentSlot ──────────────────────────────────────────────────────────

class TestAppointmentSlot:
    def test_make_id(self):
        dt = datetime(2026, 3, 16, 8, 30)
        slot_id = AppointmentSlot.make_id("https://example.pl/doc", dt)
        assert slot_id == "https://example.pl/doc_2026-03-16T08:30:00"

    def test_slot_creation(self):
        dt = datetime(2026, 3, 16, 11, 20)
        slot = AppointmentSlot(
            doctor_name="Dr Test",
            doctor_url="https://example.pl/doc",
            dt=dt,
            slot_id=AppointmentSlot.make_id("https://example.pl/doc", dt),
            location="ul. Testowa 1, Kraków",
        )
        assert slot.doctor_name == "Dr Test"
        assert slot.location == "ul. Testowa 1, Kraków"
