from __future__ import annotations

from pathlib import Path

from bybit_automation.models.app_state import AppState
from bybit_automation.services.settings_service import JsonSettingsService


def test_load_returns_default_state_when_file_is_missing(tmp_path: Path) -> None:
    service = JsonSettingsService(tmp_path / "settings.json")

    state = service.load()

    assert state == AppState()


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    service = JsonSettingsService(tmp_path / "settings.json")
    state = AppState()
    state.advertisement.trade_side = "Продажа"
    state.advertisement.fixed_price = "99,50"
    state.advertisement.notes = "Hello"
    state.advertisement.security_password = "Secret1337$"
    state.search.depth = "7"

    service.save(state)
    loaded = service.load()

    assert loaded == state
