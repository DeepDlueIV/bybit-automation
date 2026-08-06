from __future__ import annotations

from pathlib import Path

import pytest

from bybit_automation.infrastructure.portable_chrome_browser_driver import (
    PortableChromeBrowserDriver,
)
from bybit_automation.models.browser_discovery import BrowserDiscoveryResult, BrowserTabInfo
from bybit_automation.services.logging_service import AppLogger


def make_driver(tmp_path: Path) -> PortableChromeBrowserDriver:
    return PortableChromeBrowserDriver(
        logger=AppLogger(),
        chrome_executable=tmp_path / "runtime" / "chrome-win64" / "chrome.exe",
        user_data_dir=tmp_path / "data" / "portable-chrome-profile",
        artifacts_dir=tmp_path / "data" / "playwright-artifacts",
    )


def test_portable_chrome_opens_external_process_with_dedicated_profile(tmp_path: Path, monkeypatch) -> None:
    driver = make_driver(tmp_path)
    driver._portable_chrome_executable.parent.mkdir(parents=True)
    driver._portable_chrome_executable.touch()
    launched_commands: list[list[str]] = []

    monkeypatch.setattr(driver, "_find_existing_debug_port", lambda: None)
    monkeypatch.setattr(driver, "_find_free_port", lambda: 54321)
    monkeypatch.setattr(
        "bybit_automation.infrastructure.portable_chrome_browser_driver.subprocess.Popen",
        lambda command: launched_commands.append(command),
    )

    driver.open_profile("")

    assert launched_commands == [[
        str(driver._portable_chrome_executable),
        "--remote-debugging-port=54321",
        f"--user-data-dir={driver._user_data_dir}",
        "--remote-allow-origins=*",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]]
    assert "--disable-extensions" not in launched_commands[0]


def test_portable_chrome_does_not_launch_duplicate_for_same_profile(tmp_path: Path, monkeypatch) -> None:
    driver = make_driver(tmp_path)
    driver._portable_chrome_executable.parent.mkdir(parents=True)
    driver._portable_chrome_executable.touch()
    monkeypatch.setattr(driver, "_find_existing_debug_port", lambda: 54321)
    monkeypatch.setattr(
        "bybit_automation.infrastructure.portable_chrome_browser_driver.subprocess.Popen",
        lambda _command: (_ for _ in ()).throw(AssertionError("повторный Chrome не должен запускаться")),
    )

    driver.open_profile("")


def test_portable_chrome_reports_missing_prepared_browser(tmp_path: Path) -> None:
    driver = make_driver(tmp_path)

    with pytest.raises(RuntimeError) as error:
        driver.open_profile("")

    message = str(error.value)
    assert str(driver._portable_chrome_executable) in message
    assert "150.0.7871.124" in message
    assert "запуск.txt" in message


def test_portable_chrome_discovery_uses_own_browser_name(tmp_path: Path, monkeypatch) -> None:
    driver = make_driver(tmp_path)
    base_result = BrowserDiscoveryResult(
        browser_name="System Chrome",
        window_title="System Chrome extensions profile",
        tabs=[BrowserTabInfo(title="Bybit", role="sell")],
        sell_tab_title="Bybit",
        connected=True,
    )
    monkeypatch.setattr(
        "bybit_automation.infrastructure.playwright_browser_driver.PlaywrightBrowserDriver.discover_profile",
        lambda _driver: base_result,
    )

    result = driver.discover_profile()

    assert result.browser_name == "Portable Chrome 150"
    assert result.window_title == "Portable Chrome 150"
    assert result.tabs == base_result.tabs
    assert result.connected is True


def test_portable_chrome_close_disconnects_without_closing_external_browser(tmp_path: Path) -> None:
    driver = make_driver(tmp_path)

    class MustNotClose:
        def close(self) -> None:
            raise AssertionError("внешний Portable Chrome не должен закрываться")

    class FakePlaywright:
        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    playwright = FakePlaywright()
    driver._context = MustNotClose()
    driver._browser = MustNotClose()
    driver._playwright = playwright

    driver.close()

    assert playwright.stopped is True
    assert driver._context is None
    assert driver._browser is None


def test_portable_chrome_waits_for_bybit_overlay_before_trade_side_click(tmp_path: Path, monkeypatch) -> None:
    driver = make_driver(tmp_path)
    calls: list[str] = []

    class FakeButton:
        def __init__(self) -> None:
            self.first = self

        def filter(self, **_kwargs):
            return self

        def click(self, timeout: int) -> None:
            calls.append(f"click:{timeout}")

        def wait_for(self, timeout: int) -> None:
            calls.append(f"wait:{timeout}")

    class FakePage:
        def locator(self, _selector: str) -> FakeButton:
            return FakeButton()

    driver._ads_page = FakePage()
    monkeypatch.setattr(driver, "_dismiss_payment_modal_if_open", lambda _page: calls.append("payment"))
    monkeypatch.setattr(
        driver,
        "_wait_for_bybit_interceptors_to_clear",
        lambda _page, role: calls.append(f"overlay:{role}"),
    )
    monkeypatch.setattr(
        driver,
        "_click_and_expect",
        lambda _page, click_action, expect_action, **_kwargs: (click_action(), expect_action()),
    )

    driver.select_trade_side("Portable Chrome 150", "Покупка")

    assert calls == [
        "payment",
        "overlay:Ads form",
        f"click:{driver.READY_TIMEOUT_MS}",
        f"wait:{driver.READY_TIMEOUT_MS}",
    ]
