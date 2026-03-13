from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time

import structlog
from playwright.async_api import Page

log = structlog.get_logger(__name__)

# Polish month abbreviations -> month number
_PL_MONTHS: dict[str, int] = {
    "sty": 1, "lut": 2, "mar": 3, "kwi": 4, "maj": 5, "cze": 6,
    "lip": 7, "sie": 8, "wrz": 9, "paź": 10, "paz": 10, "lis": 11, "gru": 12,
}

# aria-label format: "08:30 Pon, 16 Mar"
_ARIA_LABEL_RE = re.compile(
    r"(\d{1,2}):(\d{2})\s+\w+,\s+(\d{1,2})\s+(\w+)",
    re.IGNORECASE,
)


@dataclass
class AppointmentSlot:
    doctor_name: str
    doctor_url: str
    dt: datetime
    slot_id: str
    location: str | None = None

    @staticmethod
    def make_id(doctor_url: str, dt: datetime) -> str:
        return f"{doctor_url}_{dt.isoformat()}"


def _parse_aria_label(label: str) -> datetime | None:
    """Parse 'HH:MM DAY_PL, DD MON_PL' -> datetime (current or next year)."""
    m = _ARIA_LABEL_RE.search(label)
    if not m:
        log.debug("aria_label_parse_failed", label=label)
        return None

    hour, minute, day_str, month_str = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4).lower()
    month = _PL_MONTHS.get(month_str)
    if not month:
        log.warning("unknown_month_abbreviation", month_str=month_str, label=label)
        return None

    today = date.today()
    year = today.year
    try:
        slot_date = date(year, month, day_str)
    except ValueError:
        return None

    # If parsed date is already in the past (> 1 day ago), assume next year
    if (today - slot_date).days > 1:
        year += 1
        try:
            slot_date = date(year, month, day_str)
        except ValueError:
            return None

    return datetime.combine(slot_date, time(hour, minute))


async def parse_available_slots(
    page: Page,
    doctor_name: str,
    doctor_url: str,
    location: str | None,
) -> list[AppointmentSlot]:
    """Extract all visible available appointment slots from the current page state."""
    buttons = await page.query_selector_all("button.calendar-slot-available")
    slots: list[AppointmentSlot] = []

    for btn in buttons:
        aria_label = await btn.get_attribute("aria-label") or ""
        dt = _parse_aria_label(aria_label)
        if dt is None:
            log.warning("slot_parse_skipped", aria_label=aria_label)
            continue

        slot_id = AppointmentSlot.make_id(doctor_url, dt)
        slots.append(AppointmentSlot(
            doctor_name=doctor_name,
            doctor_url=doctor_url,
            dt=dt,
            slot_id=slot_id,
            location=location,
        ))

    return slots


async def get_current_location(page: Page) -> str | None:
    """Extract the currently selected location name from the multiselect widget."""
    # Try the full address from multiselect (multi-location pages)
    el = await page.query_selector(".multiselect__single h5.h4")
    if el:
        text = (await el.inner_text()).strip()
        if text:
            return text

    # Fallback: look for address in doctor profile header
    el = await page.query_selector("[data-test-id='address'], .address, .dp-address")
    if el:
        text = (await el.inner_text()).strip()
        if text:
            return text

    return None
