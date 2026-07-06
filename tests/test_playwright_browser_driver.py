from __future__ import annotations

import pytest

from bybit_automation.infrastructure.playwright_browser_driver import PlaywrightBrowserDriver
from bybit_automation.models.automation_mode import AutomationMode
from bybit_automation.services.logging_service import AppLogger


def test_incogniton_cdp_mode_requires_endpoint(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.INCOGNITON_PLAYWRIGHT_CDP,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
        cdp_endpoint="",
    )

    with pytest.raises(RuntimeError, match="BYBIT_PLAYWRIGHT_CDP_ENDPOINT"):
        driver.focus("Incogniton Playwright/CDP")


def test_playwright_profile_launch_kwargs_prefer_installed_chrome(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )

    kwargs = driver._launch_persistent_context_kwargs()

    assert kwargs == {
        "headless": False,
        "viewport": {"width": 1440, "height": 1000},
        "locale": "ru-RU",
        "channel": "chrome",
        "ignore_default_args": [
            "--disable-background-networking",
            "--disable-component-extensions-with-background-pages",
            "--disable-component-update",
            "--disable-extensions",
        ],
    }


def test_incogniton_cdp_launch_kwargs_do_not_force_chrome_channel(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.INCOGNITON_PLAYWRIGHT_CDP,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
        cdp_endpoint="http://127.0.0.1:9222",
    )

    kwargs = driver._launch_persistent_context_kwargs()

    assert "channel" not in kwargs


def test_playwright_profile_fallback_keeps_extensions_enabled(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )

    kwargs = driver._launch_persistent_context_kwargs(prefer_chrome=False)

    assert "channel" not in kwargs
    assert kwargs["ignore_default_args"] == [
        "--disable-background-networking",
        "--disable-component-extensions-with-background-pages",
        "--disable-component-update",
        "--disable-extensions",
    ]


def test_playwright_profile_manual_chrome_command_keeps_extensions_enabled(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )

    command = driver._build_manual_chrome_command(
        chrome_executable=tmp_path / "chrome.exe",
        remote_debugging_port=9223,
    )

    assert command == [
        str(tmp_path / "chrome.exe"),
        "--remote-debugging-port=9223",
        f"--user-data-dir={tmp_path / 'profile'}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    assert not any("disable-extensions" in arg for arg in command)


def test_open_profile_does_not_connect_playwright_cdp_for_manual_browser(tmp_path, monkeypatch) -> None:
    launched_commands: list[list[str]] = []

    class FakeProcess:
        pass

    def fake_popen(command: list[str]):
        launched_commands.append(command)
        return FakeProcess()

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    monkeypatch.setattr(driver, "_find_chrome_executable", lambda: tmp_path / "chrome.exe")
    monkeypatch.setattr(driver, "_find_free_port", lambda: 9223)
    monkeypatch.setattr("bybit_automation.infrastructure.playwright_browser_driver.subprocess.Popen", fake_popen)
    monkeypatch.setattr(driver, "_ensure_context", lambda: (_ for _ in ()).throw(AssertionError("must not connect CDP")))

    driver.open_profile("")

    assert launched_commands == [
        [
            str(tmp_path / "chrome.exe"),
            "--remote-debugging-port=9223",
            f"--user-data-dir={tmp_path / 'profile'}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ]
    ]


def test_playwright_profile_finds_existing_debug_port_for_same_profile(tmp_path, monkeypatch) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    command_line = (
        '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
        '--remote-debugging-port=63398 '
        f'"--user-data-dir={tmp_path / "profile"}" '
        '--no-first-run about:blank'
    )

    monkeypatch.setattr(driver, "_iter_chrome_command_lines", lambda: [command_line])

    assert driver._find_existing_debug_port() == 63398


def test_extract_price_candidates_from_sell_text(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )

    candidates = driver._extract_price_candidates("Best price 79,34 RUB\nOther 80,10 RUB")

    assert candidates == ["79,34 RUB", "80,10 RUB"]


def test_select_sell_price_prefers_rub_price_over_limits(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )

    price = driver._select_sell_price(["79,87 RUB", "000,00 RUB", "7000,00", "5000,00"])

    assert price == "79,87"


def test_extract_advertisement_candidates_from_ads_text(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )

    candidates = driver._extract_advertisement_candidates(
        "ID 190362987654\n79,87 RUB\n2026-07-07 00:10:11"
    )

    assert candidates == {
        "advertisement_ids": ["190362987654"],
        "prices": ["79,87 RUB"],
        "created_at": ["2026-07-07 00:10:11"],
    }


def test_open_standard_p2p_ad_form_uses_python_locator_first_property(tmp_path, monkeypatch) -> None:
    class FakeLocator:
        @property
        def first(self):
            return self

        def __call__(self):
            raise AssertionError("Playwright Python Locator.first is a property, not a method")

        def click(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS

        def wait_for(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS

    class FakePage:
        def get_by_role(self, *args, **kwargs) -> FakeLocator:
            raise AssertionError("The Bybit post-ad button is not reliably reachable by role name")

        def get_by_text(self, *args, **kwargs) -> FakeLocator:
            return FakeLocator()

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    fake_page = FakePage()
    monkeypatch.setattr(driver, "ensure_ads_tab", lambda window_title: setattr(driver, "_ads_page", fake_page))
    monkeypatch.setattr(
        driver,
        "_click_and_expect",
        lambda page, click_action, expect_action, **kwargs: (click_action(), expect_action()),
    )

    driver.open_standard_p2p_ad_form("Playwright profile")
