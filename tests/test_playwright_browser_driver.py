from __future__ import annotations

import re

import pytest

from bybit_automation.infrastructure.playwright_browser_driver import PlaywrightBrowserDriver
from bybit_automation.models.automation_mode import AutomationMode
from bybit_automation.models.merchant_cycle import AdvertisementSnapshot
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


def test_wait_for_merchant_candidates_can_wait_for_page_content_change(tmp_path, monkeypatch) -> None:
    class FakePage:
        def __init__(self) -> None:
            self.texts = [
                "OldSeller\n100 исполнено\n100 %\n79,90 RUB",
                "OldSeller\n100 исполнено\n100 %\n79,90 RUB",
                "Mannequin\n11 исполнено\n91 %\n79,84 RUB",
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

    merchants = driver._wait_for_merchant_candidates(FakePage(), previous_candidates=["OldSeller"])

    assert merchants == ["Mannequin"]


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
        def __init__(self, close_button: FakeCloseButton | None = None) -> None:
            self.first = close_button or self
            self._close_button = close_button

        def count(self) -> int:
            return 1 if self._close_button is not None else 0

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

        def get_by_role(self, role: str, **kwargs) -> FakeButtons:
            assert role == "button"
            return FakeButtons()

        def is_visible(self) -> bool:
            return not self.close_button.clicked

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


def test_dismiss_sell_intro_modal_clicks_skip_button_when_no_close_icon(tmp_path) -> None:
    class FakeButton:
        def __init__(self, on_click=None) -> None:
            self.clicked = False
            self._on_click = on_click

        def click(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            self.clicked = True
            if self._on_click is not None:
                self._on_click()

    class FakeButtons:
        def __init__(self, button: FakeButton | None = None) -> None:
            self.first = self
            self._button = button

        def count(self) -> int:
            return 1 if self._button is not None else 0

        def click(self, timeout: int) -> None:
            assert self._button is not None
            self._button.click(timeout)

    class FakeDialog:
        def __init__(self) -> None:
            self.first = self
            self.closed = False
            self.skip = FakeButton(lambda: setattr(self, "closed", True))

        def filter(self, **kwargs):
            return self

        def count(self) -> int:
            return 1

        def locator(self, selector: str):
            assert "close" in selector or "Close" in selector
            return FakeButtons()

        def get_by_role(self, role: str, **kwargs):
            assert role == "button"
            return FakeButtons(self.skip)

        def is_visible(self) -> bool:
            return not self.closed

    class FakePage:
        def __init__(self) -> None:
            self.dialog = FakeDialog()
            self.waited = False

        def get_by_role(self, role: str):
            assert role == "dialog"
            return self.dialog

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

    assert fake_page.dialog.skip.clicked is True
    assert fake_page.waited is True


def test_ensure_sell_tab_dismisses_intro_modal_on_page_entry(tmp_path, monkeypatch) -> None:
    class FakePage:
        url = PlaywrightBrowserDriver.SELL_URL

        def __init__(self) -> None:
            self.dismissed = False

        def bring_to_front(self) -> None:
            pass

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            assert state == "domcontentloaded"
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    context = FakeContext()
    monkeypatch.setattr(driver, "_ensure_context", lambda: context)
    monkeypatch.setattr(driver, "_dismiss_startup_useless_modal_if_open", lambda page, role: None)
    monkeypatch.setattr(driver, "_dismiss_sell_intro_modal_if_open", lambda page: setattr(page, "dismissed", True))

    driver.ensure_sell_tab("Playwright profile")

    assert context.pages[0].dismissed is True


def test_refresh_page_dismisses_sell_intro_modal(tmp_path, monkeypatch) -> None:
    class FakePage:
        def __init__(self) -> None:
            self.dismissed = False

        def reload(self, *, wait_until: str, timeout: int) -> None:
            assert wait_until == "domcontentloaded"
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    page = FakePage()
    driver._sell_page = page
    monkeypatch.setattr(driver, "_dismiss_sell_intro_modal_if_open", lambda page: setattr(page, "dismissed", True))

    driver.refresh_page("Playwright profile")

    assert page.dismissed is True


def test_ensure_ads_tab_reuses_cached_page_without_startup_modal_probe(tmp_path, monkeypatch) -> None:
    class FakePage:
        url = PlaywrightBrowserDriver.ADS_URL

        def __init__(self) -> None:
            self.brought_to_front = False

        def bring_to_front(self) -> None:
            self.brought_to_front = True

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    page = FakePage()
    driver._ads_page = page
    monkeypatch.setattr(driver, "_ensure_context", lambda: (_ for _ in ()).throw(AssertionError("cached page is enough")))
    monkeypatch.setattr(
        driver,
        "_dismiss_startup_useless_modal_if_open",
        lambda page, role: (_ for _ in ()).throw(AssertionError("startup probe should not repeat for cached page")),
    )

    driver.ensure_ads_tab("Playwright profile")

    assert driver._ads_page is page
    assert page.brought_to_front is False


def test_page_for_url_navigates_cached_ads_page_instead_of_opening_duplicate_tab(tmp_path, monkeypatch) -> None:
    class FakePage:
        def __init__(self) -> None:
            self.url = "https://www.bybit.com/ru-RU/p2p/merchant-admin/ads/create"
            self.navigated_to = ""

        def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
            assert wait_until == "commit"
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            self.navigated_to = url
            self.url = url

    class FakeContext:
        pages: list[FakePage] = []

        def new_page(self):
            raise AssertionError("must not open a duplicate Ads tab")

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    page = FakePage()
    driver._ads_page = page
    monkeypatch.setattr(driver, "_ensure_context", lambda: FakeContext())
    monkeypatch.setattr(driver, "_wait_for_domcontentloaded_best_effort", lambda page, role: None)
    monkeypatch.setattr(driver, "_dismiss_startup_useless_modal_if_open", lambda page, role: None)

    result = driver._page_for_url(PlaywrightBrowserDriver.ADS_URL, role="Ads")

    assert result is page
    assert page.navigated_to == PlaywrightBrowserDriver.ADS_URL


def test_ensure_sell_tab_navigates_cached_buy_page_back_to_sell(tmp_path, monkeypatch) -> None:
    class FakePage:
        def __init__(self) -> None:
            self.url = "https://www.bybit.com/ru-RU/p2p/buy/USDT/RUB"
            self.navigated_to = ""

        def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
            assert wait_until == "commit"
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            self.navigated_to = url
            self.url = url

    class FakeContext:
        pages: list[FakePage] = []

        def new_page(self):
            raise AssertionError("must reuse cached Sell tab instead of opening a duplicate")

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    page = FakePage()
    driver._sell_page = page
    monkeypatch.setattr(driver, "_ensure_context", lambda: FakeContext())
    monkeypatch.setattr(driver, "_wait_for_domcontentloaded_best_effort", lambda page, role: None)
    monkeypatch.setattr(driver, "_dismiss_startup_useless_modal_if_open", lambda page, role: None)
    monkeypatch.setattr(driver, "_dismiss_sell_intro_modal_if_open", lambda page: None)

    driver.ensure_sell_tab("Playwright profile")

    assert driver._sell_page is page
    assert page.navigated_to == PlaywrightBrowserDriver.SELL_URL


def test_onboarding_intro_text_is_not_treated_as_critical_dialog(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )

    assert not driver._looks_like_critical_cycle_dialog(
        "Начало работы с Bybit P2P Покупайте криптовалюту у других пользователей "
        "Выберите предпочитаемую валюту, криптовалюту и P2P-объявление. "
        "Убедитесь, что мейкер принимает выбранный способ оплаты. Торговать"
    )


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
            self.label_lookups = 0

        def get_by_label(self, *args, **kwargs):
            self.label_lookups += 1
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
    assert page.label_lookups == 0


def test_enter_security_password_does_not_wait_for_page_load_after_confirm(tmp_path, monkeypatch) -> None:
    class FakeConfirmButton:
        def __init__(self) -> None:
            self.first = self
            self.clicked = False

        def or_(self, other):
            return self

        def click(self, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            self.clicked = True

    class FakePasswordDialog:
        def __init__(self) -> None:
            self.first = self

        def count(self) -> int:
            return 0

        def is_visible(self) -> bool:
            return False

        def nth(self, index: int):
            raise AssertionError("no password fields should be inspected when count is zero")

    class FakePage:
        def __init__(self) -> None:
            self.confirm = FakeConfirmButton()

        def get_by_role(self, role: str, **kwargs):
            assert role == "button"
            return self.confirm

        def get_by_text(self, *args, **kwargs):
            return FakePasswordDialog()

        def locator(self, selector: str):
            assert selector == 'input[type="password"]'
            return FakePasswordDialog()

        def wait_for_load_state(self, *args, **kwargs) -> None:
            raise AssertionError("confirming financial password must not wait for page load")

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    page = FakePage()
    driver._ads_page = page
    monkeypatch.setattr(driver, "_fill_security_password_field", lambda page, password: None)

    driver.enter_security_password("Playwright profile", "secret")

    assert page.confirm.clicked is True


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


def test_transaction_limits_are_filled_by_label_not_placeholder(tmp_path) -> None:
    class FakeInput:
        def __init__(self) -> None:
            self.first = self
            self.value = ""

        def fill(self, value: str, timeout: int) -> None:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            self.value = value

    class FakePage:
        def __init__(self) -> None:
            self.minimum = FakeInput()
            self.maximum = FakeInput()
            self.selectors: list[str] = []

        def locator(self, selector: str):
            self.selectors.append(selector)
            if "Мин. сумма транзакции" in selector:
                return self.minimum
            if "Макс. сумма транзакции" in selector:
                return self.maximum
            raise AssertionError(f"unexpected selector: {selector}")

    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.PLAYWRIGHT_PROFILE,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
    )
    page = FakePage()
    driver._ads_page = page

    driver.set_minimum_transaction("Playwright profile", "5000")
    driver.set_maximum_transaction("Playwright profile", "3500000")

    assert page.minimum.value == "5000"
    assert page.maximum.value == "3500000"
    assert all('placeholder="500"' not in selector for selector in page.selectors)


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


def test_find_icon_button_by_tooltip_falls_back_to_role_buttons(tmp_path) -> None:
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
            self.buttons = [FakeButton(self, "Редактировать"), FakeButton(self, "Удалить")]
            self.selectors: list[str] = []

        def locator(self, selector: str):
            self.selectors.append(selector)
            if selector == ".moly-iconbutton":
                return FakeButtons([])
            if selector == 'button, [role="button"], [aria-label], [class*="icon"], [class*="Icon"]':
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


def test_delete_current_advertisement_scopes_tooltip_icon_search_to_ad_row(tmp_path, monkeypatch) -> None:
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

    class FakeCollection:
        def __init__(self, items: list[FakeButton], first=None) -> None:
            self._items = items
            self.last = self
            self.first = first if first is not None else self

        def count(self) -> int:
            return len(self._items)

        def nth(self, index: int) -> FakeButton:
            return self._items[index]

        def click(self, timeout: int) -> None:
            if self._items:
                self._items[-1].click(timeout)

        def wait_for(self, *args, **kwargs) -> None:
            pass

    class FakeText:
        def __init__(self, row: FakeRow) -> None:
            self._row = row

        def locator(self, selector: str):
            assert "ancestor" in selector
            return self._row

        def wait_for(self, *args, **kwargs) -> None:
            pass

    class FakeRow:
        def __init__(self, page: FakePage) -> None:
            self.row_edit = FakeButton(page, "Изменить")
            self.row_delete = FakeButton(page, "Удалить")

        def get_by_role(self, *args, **kwargs):
            return FakeCollection([])

        def locator(self, selector: str):
            if selector == ".moly-iconbutton":
                return FakeCollection([])
            if selector == 'button, [role="button"], [aria-label], [class*="icon"], [class*="Icon"]':
                return FakeCollection([self.row_edit, self.row_delete])
            raise AssertionError(selector)

    class FakeBody:
        def __init__(self, page: FakePage) -> None:
            self._page = page

        def inner_text(self, timeout: int) -> str:
            assert timeout == PlaywrightBrowserDriver.READY_TIMEOUT_MS
            return self._page.tooltip

    class FakePage:
        def __init__(self) -> None:
            self.url = PlaywrightBrowserDriver.ADS_URL
            self.tooltip = ""
            self.global_delete = FakeButton(self, "Удалить")
            self.row = FakeRow(self)

        def get_by_text(self, text, **kwargs):
            assert text == "ad-1"
            return FakeText(self.row)

        def get_by_role(self, *args, **kwargs):
            return FakeCollection([], first=FakeCollection([]))

        def locator(self, selector: str):
            if selector == "body":
                return FakeBody(self)
            if selector == ".moly-iconbutton":
                return FakeCollection([])
            if selector == 'button, [role="button"], [aria-label], [class*="icon"], [class*="Icon"]':
                return FakeCollection([self.global_delete])
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
    driver._ads_page = page
    monkeypatch.setattr(
        driver,
        "read_current_advertisement",
        lambda window_title: AdvertisementSnapshot("ad-1", "76,40", "Покупка"),
    )
    monkeypatch.setattr(
        driver,
        "_click_and_expect",
        lambda page, click_action, expect_action, **kwargs: click_action(),
    )

    driver.delete_current_advertisement("Playwright profile")

    assert page.global_delete.clicked is False
    assert page.row.row_delete.clicked is True
