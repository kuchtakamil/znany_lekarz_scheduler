from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from znany_lekarz_scheduler.monitor.state_manager import StateManager
from znany_lekarz_scheduler.scraper.slots_parser import AppointmentSlot


def _make_slot(hour: int, minute: int = 0) -> AppointmentSlot:
    dt = datetime(2026, 3, 16, hour, minute)
    url = "https://example.pl/doc"
    return AppointmentSlot(
        doctor_name="Dr Test",
        doctor_url=url,
        dt=dt,
        slot_id=AppointmentSlot.make_id(url, dt),
        location="Kraków",
    )


class TestLoadKnownSlots:
    def test_missing_file_returns_empty_set(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path / "nonexistent.json")
        assert sm.load_known_slots() == set()

    def test_loads_ids_from_file(self, tmp_path: Path) -> None:
        state_file = tmp_path / "known_slots.json"
        ids = ["id_a", "id_b", "id_c"]
        state_file.write_text(json.dumps(ids), encoding="utf-8")

        sm = StateManager(state_file)
        assert sm.load_known_slots() == set(ids)

    def test_corrupted_file_returns_empty_set(self, tmp_path: Path) -> None:
        state_file = tmp_path / "known_slots.json"
        state_file.write_text("not valid json", encoding="utf-8")

        sm = StateManager(state_file)
        assert sm.load_known_slots() == set()


class TestSaveKnownSlots:
    def test_creates_file_and_parent_dirs(self, tmp_path: Path) -> None:
        state_file = tmp_path / "a" / "b" / "known_slots.json"
        sm = StateManager(state_file)
        sm.save_known_slots({"id_x", "id_y"})

        assert state_file.exists()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert set(data) == {"id_x", "id_y"}

    def test_output_is_sorted(self, tmp_path: Path) -> None:
        state_file = tmp_path / "known_slots.json"
        sm = StateManager(state_file)
        sm.save_known_slots({"id_z", "id_a", "id_m"})

        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data == sorted(data)

    def test_roundtrip(self, tmp_path: Path) -> None:
        state_file = tmp_path / "known_slots.json"
        sm = StateManager(state_file)
        original = {"slot_1", "slot_2", "slot_3"}
        sm.save_known_slots(original)
        assert sm.load_known_slots() == original


class TestFindNewSlots:
    def test_all_new_when_known_empty(self) -> None:
        sm = StateManager()
        slots = [_make_slot(8), _make_slot(9), _make_slot(10)]
        new = sm.find_new_slots(slots, set())
        assert new == slots

    def test_no_new_when_all_known(self) -> None:
        sm = StateManager()
        slots = [_make_slot(8), _make_slot(9)]
        known = {s.slot_id for s in slots}
        assert sm.find_new_slots(slots, known) == []

    def test_returns_only_unknown_slots(self) -> None:
        sm = StateManager()
        slot_old = _make_slot(8)
        slot_new = _make_slot(9)
        known = {slot_old.slot_id}
        result = sm.find_new_slots([slot_old, slot_new], known)
        assert result == [slot_new]

    def test_result_sorted_by_datetime(self) -> None:
        sm = StateManager()
        slots = [_make_slot(11), _make_slot(8), _make_slot(9, 30)]
        new = sm.find_new_slots(slots, set())
        assert [s.dt.hour for s in new] == [8, 9, 11]

    def test_empty_current_returns_empty(self) -> None:
        sm = StateManager()
        assert sm.find_new_slots([], {"some_id"}) == []
