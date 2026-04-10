from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, field_validator


class DoctorConfig(BaseModel):
    name: str
    url: str
    speciality: str | None = None
    check_priority: int = 1  # 1=high, 3=low
    earlier_than: date | None = None  # notify only if slot is before this date


class ScheduleConfig(BaseModel):
    check_interval_minutes: int = 45
    active_hours_start: time = time(7, 0)
    active_hours_end: time = time(22, 30)
    active_days: list[str] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    jitter_percent: int = 25

    @field_validator("active_hours_start", "active_hours_end", mode="before")
    @classmethod
    def parse_time(cls, v: str | time) -> time:
        if isinstance(v, time):
            return v
        h, m = v.split(":")
        return time(int(h), int(m))


class BrowserConfig(BaseModel):
    headless: bool = True
    browser_type: Literal["chromium", "firefox"] = "chromium"
    viewport_width: int = 1366
    viewport_height: int = 768
    locale: str = "pl-PL"
    timezone: str = "Europe/Warsaw"
    user_data_dir: str | None = None


class NotificationConfig(BaseModel):
    apprise_urls: list[str] = []
    cooldown_minutes: int = 120


class AppConfig(BaseModel):
    doctors: list[DoctorConfig]
    schedule: ScheduleConfig = ScheduleConfig()
    browser: BrowserConfig = BrowserConfig()
    notifications: NotificationConfig = NotificationConfig()
    login_email: str
    login_password: str
