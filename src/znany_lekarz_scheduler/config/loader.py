from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import AppConfig, BrowserConfig, DoctorConfig, NotificationConfig, ScheduleConfig


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ZNANY_LEKARZ_", env_file=".env", env_file_encoding="utf-8")

    email: str
    password: str


def load_config(config_path: Path = Path("config.toml")) -> AppConfig:
    env = EnvSettings()  # type: ignore[call-arg]

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}. Copy config.example.toml to config.toml and edit it.")

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    doctors = [DoctorConfig(**d) for d in raw.get("doctors", [])]
    schedule = ScheduleConfig(**raw.get("schedule", {}))
    browser = BrowserConfig(**raw.get("browser", {}))
    notifications = NotificationConfig(**raw.get("notifications", {}))

    return AppConfig(
        doctors=doctors,
        schedule=schedule,
        browser=browser,
        notifications=notifications,
        login_email=env.email,
        login_password=env.password,
    )
