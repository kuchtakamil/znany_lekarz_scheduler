from __future__ import annotations

import json
from pathlib import Path

import structlog

from ..scraper.slots_parser import AppointmentSlot

log = structlog.get_logger(__name__)

_DEFAULT_STATE_PATH = Path("data/state/known_slots.json")


class StateManager:
    """Persists known slot IDs and computes diffs between scraper runs."""

    def __init__(self, path: Path = _DEFAULT_STATE_PATH) -> None:
        self._path = path

    def has_state(self) -> bool:
        """Return True if a persisted state file exists."""
        return self._path.exists()

    def load_known_slots(self) -> set[str]:
        """Return the set of slot IDs from the last saved state."""
        if not self._path.exists():
            log.debug("state_file_not_found", path=str(self._path))
            return set()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            ids = set(data)
            log.debug("state_loaded", count=len(ids), path=str(self._path))
            return ids
        except Exception as exc:
            log.warning("state_load_error", path=str(self._path), error=str(exc))
            return set()

    def save_known_slots(self, slot_ids: set[str]) -> None:
        """Persist the given set of slot IDs to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(sorted(slot_ids), indent=2), encoding="utf-8"
        )
        log.debug("state_saved", count=len(slot_ids), path=str(self._path))

    def find_new_slots(
        self,
        current_slots: list[AppointmentSlot],
        known_ids: set[str],
    ) -> list[AppointmentSlot]:
        """Return slots whose IDs are not in *known_ids*, sorted by datetime."""
        new = [s for s in current_slots if s.slot_id not in known_ids]
        new.sort(key=lambda s: s.dt)
        log.info("diff_computed", current=len(current_slots), known=len(known_ids), new=len(new))
        return new
