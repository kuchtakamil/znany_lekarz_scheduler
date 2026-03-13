from __future__ import annotations

from abc import ABC, abstractmethod

from ..scraper.slots_parser import AppointmentSlot


class BaseNotifier(ABC):
    @abstractmethod
    async def send_new_slots(self, slots: list[AppointmentSlot]) -> None:
        """Send a notification for newly discovered appointment slots."""

    @abstractmethod
    async def send_test(self) -> None:
        """Send a test notification to verify channel configuration."""
