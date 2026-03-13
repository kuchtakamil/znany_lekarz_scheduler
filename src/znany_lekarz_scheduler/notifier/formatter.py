from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ..scraper.slots_parser import AppointmentSlot

# Polish weekday abbreviations (Monday=0)
_PL_WEEKDAYS = ["Pon", "Wt", "Sr", "Czw", "Pt", "Sob", "Nd"]

# Polish month abbreviations (1-indexed)
_PL_MONTHS = [
    "", "sty", "lut", "mar", "kwi", "maj", "cze",
    "lip", "sie", "wrz", "paz", "lis", "gru",
]


def _format_dt(dt: datetime) -> str:
    weekday = _PL_WEEKDAYS[dt.weekday()]
    month = _PL_MONTHS[dt.month]
    return f"{weekday} {dt.day} {month} {dt.hour:02d}:{dt.minute:02d}"


def format_new_slots(slots: list[AppointmentSlot]) -> tuple[str, str]:
    """Return (title, body) notification text for a list of new slots.

    Slots are grouped by doctor. The title summarises the count;
    the body lists each doctor's slots with location and booking URL.
    """
    grouped: dict[str, list[AppointmentSlot]] = defaultdict(list)
    for slot in slots:
        grouped[slot.doctor_url].append(slot)

    doctor_count = len(grouped)
    slot_count = len(slots)

    title = (
        f"Nowe terminy ({slot_count})"
        if doctor_count == 1
        else f"Nowe terminy ({slot_count}) u {doctor_count} lekarzy"
    )

    parts: list[str] = []
    for url, doctor_slots in grouped.items():
        doctor_slots.sort(key=lambda s: s.dt)
        first = doctor_slots[0]
        header = first.doctor_name
        if first.location:
            header += f" | {first.location}"
        times = ", ".join(_format_dt(s.dt) for s in doctor_slots)
        parts.append(f"{header}\n{times}\n{url}")

    body = "\n\n".join(parts)
    return title, body


def format_test_message() -> tuple[str, str]:
    """Return a (title, body) pair for a test notification."""
    return "Test powiadomienia", "Powiadomienia dzialaja poprawnie."
