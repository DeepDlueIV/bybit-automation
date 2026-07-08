from __future__ import annotations

import re

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


def test_playwright_profile_manual_chrome_command_disables_extensions_for_stable_testing(tmp_path) -> None:
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
        "--disable-extensions",
        "about:blank",
    ]


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
            "--disable-extensions",
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


def test_extract_merchant_candidates_from_bybit_split_lines(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )

    merchants = driver._extract_merchant_candidates(
        "🎆\n"
        "🎆UserTether🀄\n"
        "866\xa0исполнено\n"
        "|\n"
        "100\xa0%\n"
        "76,19 RUB\n"
        "🩸bluora\n"
        "432\xa0исполнено\n"
        "76,19 RUB\n"
    )

    assert merchants == ["UserTether", "bluora"]


def test_wait_for_merchant_candidates_retries_until_seller_list_renders(tmp_path, monkeypatch) -> None:
    class FakePage:
        def __init__(self) -> None:
            self.texts = [
                "Продажа USDT за RUB через P2P\nНе обновлять",
                "🎆UserTether🀄\n866\xa0исполнено\n100\xa0%\n76,19 RUB",
            ]

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            assert state == "domcontentloaded"
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS

        def locator(self, selector: str):
            assert selector == "body"
            return self

        def inner_text(self, timeout: int) -> str:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            return self.texts.pop(0)

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    monkeypatch.setattr("bybit_automation.infrastructure.playwright_browser_driver.time.sleep", lambda seconds: None)

    merchants = driver._wait_for_merchant_candidates(FakePage())

    assert merchants == ["UserTether"]


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


def test_extract_advertisement_snapshot_prefers_price_after_limits(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )

    snapshot = driver._extract_advertisement_snapshot_from_text(
        "Покупка  USDT\n"
        "2026-07-07 15:45:13\n"
        "\t2074414418429661184\t\n"
        "20 000\n"
        "4000,00 - 3 500 000,00 RUB\n"
        "\t\n"
        "78,12 RUB\n"
        "\t0%\n"
        "Cash Deposit to Bank\n"
        "Mobile Top-up\n"
        "Bank Transfer\n"
        "\tНа листинге"
    )

    assert snapshot is not None
    assert snapshot.advertisement_id == "2074414418429661184"
    assert snapshot.price == "78,12"
    assert snapshot.side == "Покупка"
    assert snapshot.created_at == "2026-07-07 15:45:13"


def test_read_current_advertisement_waits_for_ads_body_to_render(tmp_path, monkeypatch) -> None:
    class FakeBody:
        def __init__(self, page: FakePage) -> None:
            self._page = page

        def inner_text(self, timeout: int) -> str:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            return self._page.texts.pop(0)

    class FakePage:
        def __init__(self) -> None:
            self.texts = [
                "",
                "Покупка USDT\n2026-07-07 15:45:13\n2074414418429661184\n78,12 RUB\nНа листинге",
            ]

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            assert state == "domcontentloaded"
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS

        def locator(self, selector: str) -> FakeBody:
            assert selector == "body"
            return FakeBody(self)

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    fake_page = FakePage()
    monkeypatch.setattr(driver, "ensure_ads_tab", lambda window_title: setattr(driver, "_ads_page", fake_page))
    monkeypatch.setattr("bybit_automation.infrastructure.playwright_browser_driver.time.sleep", lambda seconds: None)

    snapshot = driver.read_current_advertisement("Playwright profile")

    assert snapshot is not None
    assert snapshot.advertisement_id == "2074414418429661184"
    assert snapshot.price == "78,12"


def test_dismiss_sell_intro_modal_clicks_dialog_close_button(tmp_path) -> None:
    class FakeCloseButton:
        def __init__(self) -> None:
            self.clicked = False

        def click(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            self.clicked = True

    class FakeButtons:
        def __init__(self, close_button: FakeCloseButton) -> None:
            self.first = close_button

        def count(self) -> int:
            return 1

    class FakeDialog:
        def __init__(self, close_button: FakeCloseButton) -> None:
            self.first = self
            self.close_button = close_button

        def filter(self, **kwargs):
            assert "has_text" in kwargs
            return self

        def count(self) -> int:
            return 1

        def locator(self, selector: str) -> FakeButtons:
            assert "aria-label" in selector
            assert selector.strip() != "button"
            return FakeButtons(self.close_button)

    class FakePage:
        def __init__(self) -> None:
            self.close_button = FakeCloseButton()
            self.waited = False

        def get_by_role(self, role: str) -> FakeDialog:
            assert role == "dialog"
            return FakeDialog(self.close_button)

        def wait_for_timeout(self, milliseconds: int) -> None:
            assert milliseconds == 300
            self.waited = True

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    fake_page = FakePage()

    driver._dismiss_sell_intro_modal_if_open(fake_page)

    assert fake_page.close_button.clicked is True
    assert fake_page.waited is True


def test_dismiss_startup_useless_modal_clicks_dialog_close_button(tmp_path) -> None:
    class FakeButton:
        def __init__(self) -> None:
            self.clicked = False

        def click(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            self.clicked = True

    class FakeButtons:
        def __init__(self, button: FakeButton) -> None:
            self.first = button

        def count(self) -> int:
            return 1

    class FakeDialog:
        def __init__(self, button: FakeButton) -> None:
            self.first = self
            self._button = button

        def count(self) -> int:
            return 1

        def inner_text(self, timeout: int) -> str:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            return "Бонусный центр Новые преимущества"

        def locator(self, selector: str) -> FakeButtons:
            assert "aria-label" in selector
            assert selector.strip() != "button"
            return FakeButtons(self._button)

    class FakePage:
        def __init__(self) -> None:
            self.button = FakeButton()
            self.waited = False

        def get_by_role(self, role: str) -> FakeDialog:
            assert role == "dialog"
            return FakeDialog(self.button)

        def wait_for_timeout(self, milliseconds: int) -> None:
            assert milliseconds == 300
            self.waited = True

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    fake_page = FakePage()

    driver._dismiss_startup_useless_modal_if_open(fake_page, role="Sell")

    assert fake_page.button.clicked is True
    assert fake_page.waited is True


def test_dismiss_startup_useless_modal_keeps_critical_form_dialogs(tmp_path) -> None:
    class FakeButtons:
        def count(self) -> int:
            return 1

        @property
        def first(self):
            raise AssertionError("critical dialog must not be closed")

    class FakeDialog:
        first = None

        def __init__(self) -> None:
            self.first = self

        def count(self) -> int:
            return 1

        def inner_text(self, timeout: int) -> str:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            return "Финансовый пароль Подтвердить"

        def locator(self, selector: str) -> FakeButtons:
            assert "button" in selector
            return FakeButtons()

    class FakePage:
        def __init__(self) -> None:
            self.waited = False

        def get_by_role(self, role: str) -> FakeDialog:
            assert role == "dialog"
            return FakeDialog()

        def wait_for_timeout(self, milliseconds: int) -> None:
            self.waited = True

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    fake_page = FakePage()

    driver._dismiss_startup_useless_modal_if_open(fake_page, role="Ads")

    assert fake_page.waited is False


def test_fill_security_password_falls_back_to_visible_password_input(tmp_path, monkeypatch) -> None:
    class FakePasswordField:
        def __init__(self) -> None:
            self.value = ""

        def is_visible(self) -> bool:
            return True

        def fill(self, value: str, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            self.value = value

    class FakePasswordInputs:
        def __init__(self, field: FakePasswordField) -> None:
            self.field = field

        def count(self) -> int:
            return 1

        def nth(self, index: int) -> FakePasswordField:
            assert index == 0
            return self.field

    class FakePage:
        def __init__(self) -> None:
            self.field = FakePasswordField()

        def get_by_label(self, *args, **kwargs):
            raise RuntimeError("label is not attached")

        def locator(self, selector: str) -> FakePasswordInputs:
            assert selector == 'input[type="password"]'
            return FakePasswordInputs(self.field)

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    page = FakePage()
    monkeypatch.setattr(driver, "_save_failure_artifact", lambda page, step_name: None)

    driver._fill_security_password_field(page, "secret")

    assert page.field.value == "secret"


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


def test_submit_advertisement_waits_for_security_password_dialog(tmp_path, monkeypatch) -> None:
    class FakeLocator:
        def __init__(self, *, count: int = 0) -> None:
            self.first = self
            self.last = self
            self._count = count

        def or_(self, other):
            return self

        def count(self) -> int:
            return self._count

        def is_visible(self) -> bool:
            return self._count > 0

        def click(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS

    class FakePage:
        def __init__(self) -> None:
            self.probes = 0

        def get_by_role(self, *args, **kwargs):
            return FakeLocator(count=1)

        def get_by_text(self, *args, **kwargs):
            return FakeLocator(count=1 if "Финансовый" in str(args[0]) else 0)

        def locator(self, selector: str) -> FakeLocator:
            assert selector == 'input[type="password"]'
            self.probes += 1
            return FakeLocator(count=0)

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    driver._ads_page = FakePage()
    monkeypatch.setattr("bybit_automation.infrastructure.playwright_browser_driver.time.sleep", lambda seconds: None)

    driver.submit_advertisement("Playwright profile")


def test_submit_advertisement_clicks_last_exact_submit_text_not_header(tmp_path, monkeypatch) -> None:
    class FakeTextTargets:
        def __init__(self) -> None:
            self.first_clicked = False
            self.last_clicked = False
            self.first = self
            self.last = self

        def count(self) -> int:
            return 2

        def click(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            self.last_clicked = True

    class FakeLocator:
        first = None

        def __init__(self, *, count: int = 0) -> None:
            self.first = self
            self._count = count

        def count(self) -> int:
            return self._count

        def is_visible(self) -> bool:
            return self._count > 0

    class FakePage:
        def __init__(self) -> None:
            self.submit_targets = FakeTextTargets()

        def get_by_text(self, *args, **kwargs):
            if kwargs.get("exact") is True and args[0] == "Разместить объявления":
                return self.submit_targets
            return FakeLocator(count=1 if "Финансовый" in str(args[0]) else 0)

        def locator(self, selector: str) -> FakeLocator:
            assert selector == 'input[type="password"]'
            return FakeLocator(count=0)

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    page = FakePage()
    driver._ads_page = page
    monkeypatch.setattr("bybit_automation.infrastructure.playwright_browser_driver.time.sleep", lambda seconds: None)

    driver.submit_advertisement("Playwright profile")

    assert page.submit_targets.last_clicked is True


def test_submit_advertisement_fails_before_password_when_next_step_missing(tmp_path, monkeypatch) -> None:
    class FakeLocator:
        first = None

        def __init__(self) -> None:
            self.first = self
            self.last = self

        def or_(self, other):
            return self

        def count(self) -> int:
            return 0

        def is_visible(self) -> bool:
            return False

        def click(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS

    class FakePage:
        def get_by_role(self, *args, **kwargs):
            return FakeLocator()

        def get_by_text(self, *args, **kwargs):
            return FakeLocator()

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator()

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    driver._ads_page = FakePage()
    monkeypatch.setattr("bybit_automation.infrastructure.playwright_browser_driver.time.sleep", lambda seconds: None)
    ticks = iter([0, 31])
    monkeypatch.setattr("bybit_automation.infrastructure.playwright_browser_driver.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr(driver, "_save_failure_artifact", lambda page, step_name: None)

    with pytest.raises(RuntimeError, match="не появился следующий шаг"):
        driver.submit_advertisement("Playwright profile")


def test_submit_advertisement_does_not_treat_static_limits_as_validation_error(tmp_path, monkeypatch) -> None:
    class FakeLocator:
        first = None

        def __init__(self, *, count: int = 0) -> None:
            self.first = self
            self._count = count

        def or_(self, other):
            return self

        def count(self) -> int:
            return self._count

        def is_visible(self) -> bool:
            return self._count > 0

        def click(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS

    class FakePage:
        def get_by_role(self, *args, **kwargs):
            return FakeLocator(count=1)

        def get_by_text(self, *args, **kwargs):
            pattern = str(args[0])
            if "Финансовый" in pattern or "Fund Password" in pattern:
                return FakeLocator(count=0)
            if "лимит" in pattern or "limit" in pattern:
                return FakeLocator(count=1)
            return FakeLocator(count=0)

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(count=0)

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    page = FakePage()
    monkeypatch.setattr("bybit_automation.infrastructure.playwright_browser_driver.time.sleep", lambda seconds: None)
    ticks = iter([0, 31])
    monkeypatch.setattr("bybit_automation.infrastructure.playwright_browser_driver.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr(driver, "_save_failure_artifact", lambda page, step_name: None)

    with pytest.raises(RuntimeError, match="не появился следующий шаг"):
        driver._wait_for_submit_next_step(page)


def test_submit_validation_helper_ignores_static_form_labels(tmp_path) -> None:
    class FakePage:
        def locator(self, selector: str):
            raise AssertionError("static labels should be checked from body text only")

        def get_by_text(self, *args, **kwargs):
            raise AssertionError("static labels should not be queried with broad page regex")

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )

    assert driver._has_submit_validation_error(FakePage(), "Лимиты\nМин.\nМакс.") is False


def test_delete_current_advertisement_uses_python_locator_last_property(tmp_path, monkeypatch) -> None:
    class FakeLocator:
        @property
        def first(self):
            return self

        @property
        def last(self):
            return self

        def __call__(self):
            raise AssertionError("Playwright Python Locator.last is a property, not a method")

        def count(self) -> int:
            return 1

        def click(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS

        def wait_for(self, *args, **kwargs) -> None:
            pass

        def get_by_role(self, *args, **kwargs):
            return self

        def locator(self, *args, **kwargs):
            return self

    class FakePage:
        def get_by_text(self, *args, **kwargs):
            return FakeLocator()

        def get_by_role(self, *args, **kwargs):
            return FakeLocator()

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    driver._ads_page = FakePage()
    monkeypatch.setattr(driver, "read_current_advertisement", lambda window_title: type("S", (), {"advertisement_id": "1234567890"})())
    monkeypatch.setattr(
        driver,
        "_click_and_expect",
        lambda page, click_action, expect_action, **kwargs: (click_action(), expect_action()),
    )

    driver.delete_current_advertisement("Playwright profile")


def test_find_icon_button_by_tooltip_clicks_only_after_matching_tooltip(tmp_path) -> None:
    class FakeButton:
        def __init__(self, page: FakePage, tooltip: str) -> None:
            self._page = page
            self._tooltip = tooltip
            self.clicked = False

        def hover(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            self._page.tooltip = self._tooltip

        def click(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            self.clicked = True

        def is_visible(self) -> bool:
            return True

    class FakeButtons:
        def __init__(self, buttons: list[FakeButton]) -> None:
            self._buttons = buttons

        def count(self) -> int:
            return len(self._buttons)

        def nth(self, index: int) -> FakeButton:
            return self._buttons[index]

    class FakeBody:
        def __init__(self, page: FakePage) -> None:
            self._page = page

        def inner_text(self, timeout: int) -> str:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            return self._page.tooltip

    class FakePage:
        def __init__(self) -> None:
            self.tooltip = ""
            self.buttons = [FakeButton(self, "Изменить"), FakeButton(self, "Удалить")]

        def locator(self, selector: str):
            if selector == ".moly-iconbutton":
                return FakeButtons(self.buttons)
            if selector == "body":
                return FakeBody(self)
            raise AssertionError(selector)

        def wait_for_timeout(self, milliseconds: int) -> None:
            assert milliseconds == 300

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    page = FakePage()

    result = driver._find_icon_button_by_tooltip(page, re.compile("Удалить", re.IGNORECASE))

    result.click(timeout=PlaywrightBrowserDriver.READY_TIMEOUT_MS)
    assert page.buttons[0].clicked is False
    assert page.buttons[1].clicked is True
