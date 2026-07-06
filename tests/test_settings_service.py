from __future__ import annotations

from pathlib import Path

from bybit_automation.models.automation_mode import AutomationMode
from bybit_automation.models.app_state import AppState
from bybit_automation.services.settings_service import JsonSettingsService


def test_default_automation_mode_is_incogniton_uia() -> None:
    state = AppState()

    assert state.browser.automation_mode == AutomationMode.INCOGNITON_UIA


def test_legacy_browser_names_are_migrated() -> None:
    chrome_state = AppState.from_dict({"browser": {"browser_name": "Chrome"}})
    chromium_state = AppState.from_dict({"browser": {"browser_name": "Chromium"}})

    assert chrome_state.browser.browser_name == "System Chrome"
    assert chromium_state.browser.browser_name == "Playwright Chromium"


def test_app_paths_exposes_playwright_runtime_dirs(tmp_path: Path) -> None:
    from bybit_automation.infrastructure.paths import AppPaths

    paths = AppPaths(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        settings_file=tmp_path / "data" / "settings.json",
        found_accounts_file=tmp_path / "data" / "found_accounts.txt",
        log_file=tmp_path / "data" / "app.log",
    )

    assert paths.playwright_profile_dir == tmp_path / "data" / "playwright-profile"
    assert paths.playwright_artifacts_dir == tmp_path / "data" / "playwright-artifacts"


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
    state.browser.automation_mode = AutomationMode.PLAYWRIGHT_PROFILE
    state.search.depth = "7"

    service.save(state)
    loaded = service.load()

    assert loaded == state
