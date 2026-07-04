from __future__ import annotations

import bybit_automation.infrastructure.existing_browser_window_driver as driver_module
from bybit_automation.infrastructure.existing_browser_window_driver import ExistingBrowserWindowDriver
from bybit_automation.models.merchant_cycle import AdvertisementSnapshot, MerchantSearchResult


class FakeElementInfo:
    def __init__(self, control_type: str) -> None:
        self.control_type = control_type


class FakeControl:
    def __init__(self, title: str, control_type: str, descendants: list["FakeControl"] | None = None) -> None:
        self._title = title
        self.element_info = FakeElementInfo(control_type)
        self._descendants = descendants or []

    def window_text(self) -> str:
        return self._title

    def descendants(self) -> list["FakeControl"]:
        return self._descendants

    def parent(self):
        return self

    def invoke(self) -> None:
        return None

    @property
    def iface_invoke(self):
        class _Invoke:
            @staticmethod
            def Invoke() -> None:
                return None

        return _Invoke()

    def click_input(self) -> None:
        return None

    def set_focus(self) -> None:
        return None


class ClickTrackingControl(FakeControl):
    def __init__(
        self,
        title: str,
        control_type: str,
        clicked: list[str],
        descendants: list["FakeControl"] | None = None,
    ) -> None:
        super().__init__(title, control_type, descendants)
        self._clicked = clicked

    def click_input(self) -> None:
        self._clicked.append(self.window_text())


class NoCoordinateControl(FakeControl):
    def __init__(self, title: str, control_type: str, events: list[str]) -> None:
        super().__init__(title, control_type)
        self._events = events

    def invoke(self) -> None:
        raise RuntimeError("invoke unavailable")

    @property
    def iface_invoke(self):
        class _Invoke:
            @staticmethod
            def Invoke() -> None:
                raise RuntimeError("iface invoke unavailable")

        return _Invoke()

    def set_focus(self) -> None:
        self._events.append(f"focus:{self.window_text()}")

    def click_input(self) -> None:
        raise AssertionError("coordinate click must not be used")


class ToggleFallbackControl(NoCoordinateControl):
    def __init__(self, title: str, control_type: str, events: list[str]) -> None:
        super().__init__(title, control_type, events)
        self._checked = False

    def get_toggle_state(self) -> int:
        return int(self._checked)

    def toggle(self) -> None:
        raise RuntimeError("toggle unavailable")

    @property
    def iface_toggle(self):
        parent = self

        class _Toggle:
            @property
            def CurrentToggleState(self) -> int:
                return int(parent._checked)

            @staticmethod
            def Toggle() -> None:
                raise RuntimeError("iface toggle unavailable")

        return _Toggle()

    def mark_checked(self) -> None:
        self._checked = True


class MockLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def test_wait_until_document_contains_returns_document_when_ready(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    document = FakeControl("Bybit", "Document", [FakeControl("Цена", "Text")])
    window = FakeControl("Bybit", "Window", [document])

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    result = driver._wait_until_document_contains("Bybit", ("Цена",), timeout_seconds=1, poll_seconds=0.1)

    assert result is document


def test_wait_until_document_contains_polls_until_ready(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    state = {"ready": False}
    empty_document = FakeControl("Bybit", "Document", [])
    ready_document = FakeControl("Bybit", "Document", [FakeControl("Цена", "Text")])

    driver._find_window = lambda _: FakeControl("Bybit", "Window", [ready_document if state["ready"] else empty_document])  # type: ignore[method-assign]
    times = iter([0.0, 0.1, 0.2, 0.3])
    monkeypatch.setattr(driver_module.time, "time", lambda: next(times))

    def fake_sleep(_seconds):
        state["ready"] = True

    monkeypatch.setattr(driver_module.time, "sleep", fake_sleep)

    result = driver._wait_until_document_contains("Bybit", ("Цена",), timeout_seconds=1, poll_seconds=0.1)

    assert result.window_text() == "Bybit"


def test_read_sell_price_accepts_russian_document_title_and_data_item() -> None:
    driver = ExistingBrowserWindowDriver()
    document = FakeControl(
        "Продать USDT за RUB через криптотрейдинг на Bybit P2P",
        "Document",
        descendants=[
            FakeControl("Цена", "Text"),
            FakeControl("81,30", "DataItem"),
            FakeControl("RUB", "Text"),
        ],
    )
    window = FakeControl("Продать USDT за RUB через криптотрейдинг на Bybit P2P - ILYA BB - 1", "Window", [document])
    driver._find_window = lambda _: window  # type: ignore[method-assign]

    result = driver.read_current_sell_price(window.window_text())

    assert result == "81,30"


def test_read_sell_price_scrolls_down_after_refresh_lands_on_intro_block(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    state = {"page": "intro"}
    keys_sent: list[str] = []
    intro_document = FakeControl(
        "Buy crypto with currency via Bybit P2P Crypto Trading",
        "Document",
        descendants=[
            FakeControl("Купите USDT за RUB в три простых шага", "Text"),
            FakeControl("Шаг 1. Выберите объявление", "Text"),
        ],
    )
    listing_document = FakeControl(
        "Buy crypto with currency via Bybit P2P Crypto Trading",
        "Document",
        descendants=[
            FakeControl("Цена", "Text"),
            FakeControl("81,31 RUB", "DataItem"),
        ],
    )
    window = FakeControl("Bybit", "Window", [intro_document])

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver.focus = lambda _: None  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    def fake_find_document_by_title_part(*_args, **_kwargs):
        return intro_document if state["page"] == "intro" else listing_document

    driver._find_document_by_title_part = fake_find_document_by_title_part  # type: ignore[method-assign]

    def fake_send_keys(keys, **kwargs):
        keys_sent.append(keys)
        if keys == "{PGDN}":
            state["page"] = "listing"

    monkeypatch.setattr(driver_module, "send_keys", fake_send_keys)

    result = driver.read_current_sell_price("Bybit")

    assert result == "81,31"
    assert "{PGDN}" in keys_sent


def test_click_best_falls_back_to_keyboard_without_coordinate_click(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    events: list[str] = []
    control = NoCoordinateControl("Управление способами оплаты", "Button", events)

    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        driver_module,
        "send_keys",
        lambda keys, **kwargs: events.append(f"keys:{keys}"),
    )

    driver._click_best(control)

    assert events == ["focus:Управление способами оплаты", "keys:{ENTER}"]


def test_click_best_logs_fallback_path(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    logs: list[str] = []

    class MockLogger:
        def info(self, message: str) -> None:
            logs.append(message)

    driver._logger = MockLogger()

    # Control that fails all early fallbacks, succeeds on set_focus + send_keys
    class SetFocusFallbackControl(FakeControl):
        def invoke(self) -> None:
            raise RuntimeError("invoke unavailable")

        @property
        def iface_invoke(self):
            class _Invoke:
                @staticmethod
                def Invoke() -> None:
                    raise RuntimeError("iface invoke unavailable")
            return _Invoke()

        def select(self) -> None:
            raise RuntimeError("select unavailable")

        @property
        def iface_selection_item(self):
            class _Select:
                @staticmethod
                def Select() -> None:
                    raise RuntimeError("iface_selection_item unavailable")
            return _Select()

        def set_focus(self) -> None:
            # This is the final fallback that succeeds
            pass

    control = SetFocusFallbackControl("Тестовая кнопка", "Button")

    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        driver_module,
        "send_keys",
        lambda keys, **kwargs: None,
    )

    driver._click_best(control)

    # Verify logging happened showing which fallback was used
    assert any("click_best" in log and ("set_focus" in log or "send_keys" in log) and "Тестовая кнопка" in log for log in logs)
    driver = ExistingBrowserWindowDriver()
    events: list[str] = []
    control = ToggleFallbackControl("Bank Transfer", "CheckBox", events)

    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    def fake_send_keys(keys, **kwargs):
        events.append(f"keys:{keys}")
        if keys == " ":
            control.mark_checked()

    monkeypatch.setattr(driver_module, "send_keys", fake_send_keys)

    driver._set_checkbox_state(control, True)

    assert events == ["focus:Bank Transfer", "keys: "]


def test_refresh_page_uses_keyboard_reload(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    events: list[str] = []

    driver.focus = lambda window_title: events.append(f"focus:{window_title}")  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(driver_module, "send_keys", lambda keys, **kwargs: events.append(f"keys:{keys}"))

    driver.refresh_page("Bybit - ILYA BB - 1")

    assert events == ["focus:Bybit - ILYA BB - 1", "keys:{F5}"]


def test_click_best_rejects_forbidden_navigation_targets() -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []

    class ForbiddenControl(ClickTrackingControl):
        def invoke(self) -> None:
            clicked.append(self.window_text())

    for title in ("Все объявления", "Купить монеты", "Продать монеты", "Начинающий", "FAQ"):
        try:
            driver._click_best(ForbiddenControl(title, "Button", clicked))
        except RuntimeError as error:
            assert title in str(error)
        else:
            raise AssertionError(f"expected RuntimeError for {title}")



def test_open_standard_p2p_ad_form_clicks_popup_primary_option(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []
    window = FakeControl("Ads", "Window")

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._find_main_document = lambda _: object()  # type: ignore[method-assign]
    driver._click_best = lambda control: clicked.append(control.window_text())  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.ADS_URL  # type: ignore[method-assign]

    def fake_find_contains(root, **kwargs):
        text_part = kwargs["text_part"]
        if "разместить" in text_part.lower():
            return ClickTrackingControl("Разместить объявления", "Button", clicked)
        if "стандартная p2p-торговля" in text_part.lower():
            return FakeControl("Стандартная P2P-торговля", "Text")
        raise RuntimeError(text_part)

    monkeypatch.setattr(driver, "_find_contains", fake_find_contains)
    states = iter([False, True])
    monkeypatch.setattr(driver, "_document_contains_any_text", lambda *_: next(states), raising=False)
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.open_standard_p2p_ad_form("Bybit")

    assert clicked == ["Разместить объявления", "Стандартная P2P-торговля"]


def test_open_standard_p2p_ad_form_waits_for_popup_option(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []
    window = FakeControl("Ads", "Window")

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._find_main_document = lambda _: object()  # type: ignore[method-assign]
    driver._click_best = lambda control: clicked.append(control.window_text())  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.ADS_URL  # type: ignore[method-assign]

    attempts = iter([0, 1, 2])

    def fake_find_contains(root, **kwargs):
        text_part = kwargs["text_part"]
        if "разместить" in text_part.lower():
            return ClickTrackingControl("Разместить объявления", "Button", clicked)
        if "стандартная p2p-торговля" in text_part.lower():
            if next(attempts) < 2:
                raise RuntimeError("popup not ready")
            return FakeControl("Стандартная P2P-торговля", "Text")
        raise RuntimeError(text_part)

    monkeypatch.setattr(driver, "_find_contains", fake_find_contains)
    states = iter([False, True])
    monkeypatch.setattr(driver, "_document_contains_any_text", lambda *_: next(states), raising=False)
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.open_standard_p2p_ad_form("Bybit")

    assert clicked == ["Разместить объявления", "Стандартная P2P-торговля"]


def test_open_standard_p2p_ad_form_raises_when_popup_option_missing(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    window = FakeControl("Ads", "Window")

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._find_main_document = lambda _: object()  # type: ignore[method-assign]
    driver._click_best = lambda control: None  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.ADS_URL  # type: ignore[method-assign]

    def fake_find_contains(root, **kwargs):
        text_part = kwargs["text_part"]
        if "разместить" in text_part.lower():
            return FakeControl("Разместить объявления", "Button")
        raise RuntimeError("Не найден элемент, содержащий 'Стандартная P2P-торговля'.")

    monkeypatch.setattr(driver, "_find_contains", fake_find_contains)
    monkeypatch.setattr(driver, "_document_contains_any_text", lambda *_: False, raising=False)
    time_states = iter([0.0, 20.0])
    monkeypatch.setattr(driver_module.time, "time", lambda: next(time_states))
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    try:
        driver.open_standard_p2p_ad_form("Bybit")
    except RuntimeError as error:
        assert "Стандартная P2P-торговля" in str(error)
    else:
        raise AssertionError("expected RuntimeError")


def test_ensure_sell_tab_opens_only_missing_tab(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    window = FakeControl("Bybit - ILYA BB - 1", "Window")
    opened_urls: list[str] = []

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._tab_items = lambda _: [FakeControl("Tab 1", "TabItem"), FakeControl("Tab 2", "TabItem")]  # type: ignore[method-assign]
    driver._click_best = lambda control, **kwargs: None  # type: ignore[method-assign]
    driver._open_url_in_new_tab = lambda _, url: opened_urls.append(url)  # type: ignore[method-assign]

    urls = iter(
        [
            "https://www.bybit.com/ru-RU/p2p/merchant-admin/ads",
            "https://www.bybit.com/ru-RU/p2p/merchant-admin/ads",
            "https://www.bybit.com/ru-RU/p2p/buy/BTC/RUB",
            driver.SELL_URL,
        ]
    )
    monkeypatch.setattr(driver, "_read_current_url", lambda _: next(urls))

    driver.ensure_sell_tab("Bybit - ILYA BB - 1")

    assert opened_urls == [driver.SELL_URL]


def test_ensure_sell_tab_can_activate_browser_tab_named_buy_coins(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    window = FakeControl("Bybit - ILYA BB - 1", "Window")
    clicked_tabs: list[str] = []
    current_url = {"value": "https://www.bybit.com/ru-RU/p2p/merchant-admin/ads"}

    class BrowserTab(FakeControl):
        def invoke(self) -> None:
            clicked_tabs.append(self.window_text())
            current_url["value"] = driver.SELL_URL

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._tab_items = lambda _: [BrowserTab("Купить монеты", "TabItem")]  # type: ignore[method-assign]
    driver._read_current_url = lambda _: current_url["value"]  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.ensure_sell_tab("Bybit - ILYA BB - 1")

    assert clicked_tabs == ["Купить монеты"]


def test_ensure_sell_tab_reopens_target_in_current_tab_when_tab_switch_stays_on_wrong_url(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    window = FakeControl("Bybit - ILYA BB - 1", "Window")
    clicked_tabs: list[str] = []
    reopened_urls: list[str] = []
    opened_urls: list[str] = []
    current_url = {"value": "https://www.bybit.com/ru-RU/p2p/advertiser/create"}

    class WrongTab(FakeControl):
        def invoke(self) -> None:
            clicked_tabs.append(self.window_text())
            current_url["value"] = "https://www.bybit.com/ru-RU/p2p/advertiser/create"

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._tab_items = lambda _: [WrongTab("Продать монеты", "TabItem")]  # type: ignore[method-assign]
    driver._read_current_url = lambda _: current_url["value"]  # type: ignore[method-assign]
    driver.open_url = lambda _, url: reopened_urls.append(url) or current_url.__setitem__("value", driver.SELL_URL)  # type: ignore[method-assign]
    driver._open_url_in_new_tab = lambda _, url: opened_urls.append(url)  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.ensure_sell_tab("Bybit - ILYA BB - 1")

    assert clicked_tabs == ["Продать монеты"]
    assert reopened_urls == [driver.SELL_URL]
    assert opened_urls == []


def test_url_matches_when_browser_returns_address_without_scheme() -> None:
    driver = ExistingBrowserWindowDriver()

    assert driver._url_matches("bybit.com/ru-RU/p2p/sell/USDT/RUB", driver.SELL_URL) is True


def test_ensure_sell_tab_can_activate_browser_tab_named_buy_coins(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    window = FakeControl("Bybit - ILYA BB - 1", "Window")
    clicked_tabs: list[str] = []
    current_url = {"value": "https://www.bybit.com/ru-RU/p2p/merchant-admin/ads"}

    class BrowserTab(FakeControl):
        def invoke(self) -> None:
            clicked_tabs.append(self.window_text())
            current_url["value"] = driver.SELL_URL

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._tab_items = lambda _: [BrowserTab("Dashboard", "TabItem")]  # type: ignore[method-assign]
    driver._read_current_url = lambda _: current_url["value"]  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.ensure_sell_tab("Bybit - ILYA BB - 1")

    assert clicked_tabs == ["Dashboard"]


def test_ensure_sell_tab_reopens_target_in_current_tab_when_tab_switch_stays_on_wrong_url(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    window = FakeControl("Bybit - ILYA BB - 1", "Window")
    clicked_tabs: list[str] = []
    reopened_urls: list[str] = []
    opened_urls: list[str] = []
    current_url = {"value": "https://www.bybit.com/ru-RU/p2p/advertiser/create"}

    class WrongTab(FakeControl):
        def invoke(self) -> None:
            clicked_tabs.append(self.window_text())
            current_url["value"] = "https://www.bybit.com/ru-RU/p2p/advertiser/create"

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._tab_items = lambda _: [WrongTab("Dashboard", "TabItem")]  # type: ignore[method-assign]
    driver._read_current_url = lambda _: current_url["value"]  # type: ignore[method-assign]
    driver.open_url = lambda _, url: reopened_urls.append(url) or current_url.__setitem__("value", driver.SELL_URL)  # type: ignore[method-assign]
    driver._open_url_in_new_tab = lambda _, url: opened_urls.append(url)  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.ensure_sell_tab("Bybit - ILYA BB - 1")

    assert clicked_tabs == ["Dashboard"]
    assert reopened_urls == [driver.SELL_URL]
    assert opened_urls == []


def test_ensure_ads_tab_skips_forbidden_all_ads_tabitem(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    window = FakeControl("Bybit - ILYA BB - 1", "Window")
    clicked_tabs: list[str] = []
    current_url = {"value": driver.SELL_URL}

    class ForbiddenTab(FakeControl):
        def invoke(self) -> None:
            clicked_tabs.append(self.window_text())
            current_url["value"] = "https://www.bybit.com/ru-RU/p2p/merchant-admin/all"

    class BrowserTab(FakeControl):
        def invoke(self) -> None:
            clicked_tabs.append(self.window_text())
            current_url["value"] = driver.ADS_URL

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._tab_items = lambda _: [ForbiddenTab("Все объявления", "TabItem"), BrowserTab("Dashboard", "TabItem")]  # type: ignore[method-assign]
    driver._read_current_url = lambda _: current_url["value"]  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.ensure_ads_tab("Bybit - ILYA BB - 1")

    assert clicked_tabs == ["Dashboard"]


def test_ensure_sell_tab_fallback_uses_url_without_clicking_forbidden_all_ads_tab(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    window = FakeControl("Bybit - ILYA BB - 1", "Window")
    clicked_tabs: list[str] = []
    reopened_urls: list[str] = []
    opened_urls: list[str] = []
    current_url = {"value": driver.ADS_URL}

    class ForbiddenTab(FakeControl):
        def invoke(self) -> None:
            clicked_tabs.append(self.window_text())
            current_url["value"] = "https://www.bybit.com/ru-RU/p2p/merchant-admin/all"

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._tab_items = lambda _: [ForbiddenTab("Все объявления", "TabItem")]  # type: ignore[method-assign]
    driver._read_current_url = lambda _: current_url["value"]  # type: ignore[method-assign]
    driver.open_url = lambda _, url: reopened_urls.append(url) or current_url.__setitem__("value", driver.SELL_URL)  # type: ignore[method-assign]
    driver._open_url_in_new_tab = lambda _, url: opened_urls.append(url)  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.ensure_sell_tab("Bybit - ILYA BB - 1")

    assert clicked_tabs == []
    assert reopened_urls == [driver.SELL_URL]
    assert opened_urls == []


def test_ensure_payment_methods_clicks_visible_text_cards_when_checkbox_has_no_label(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []
    window = FakeControl("Create", "Window")
    document = FakeControl("Create document", "Document")

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._find_contains = lambda root, **kwargs: ClickTrackingControl("Управление способами оплаты", "Button", clicked) if "способами оплаты" in kwargs["text_part"].lower() else ClickTrackingControl("Подтвердить", "Button", clicked)  # type: ignore[method-assign]
    driver._set_checkbox_state = lambda control, checked: clicked.append(f"toggle:{control.window_text()}")  # type: ignore[method-assign]
    driver._click_best = lambda control: clicked.append(control.window_text())  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    bank = ClickTrackingControl("Bank Transfer", "Text", clicked)
    mobile = ClickTrackingControl("Mobile Top-up", "Text", clicked)
    cash = ClickTrackingControl("Cash Deposit to Bank", "Text", clicked)

    def fake_items(root):
        if root is document:
            return []
        return [bank, mobile, cash]

    monkeypatch.setattr(driver, "_interactive_items", fake_items)

    def fake_find_exact(root, **kwargs):
        title = kwargs["title"]
        control_types = kwargs["control_types"]
        if "CheckBox" in control_types:
            raise RuntimeError("Не найден элемент")
        for control in fake_items(root):
            if driver._item_text(control) == title and driver._item_type(control) in control_types:
                return control
        raise RuntimeError("Не найден элемент")

    driver._find_exact = fake_find_exact  # type: ignore[method-assign]

    driver.ensure_payment_methods(
        "Bybit",
        driver_module.PaymentMethodState(
            bank_transfer=True,
            mobile_top_up=True,
            cash_deposit=True,
        ),
    )

    assert clicked == [
        "Управление способами оплаты",
        "Bank Transfer",
        "Mobile Top-up",
        "Cash Deposit to Bank",
        "Подтвердить",
    ]



def test_ensure_payment_methods_waits_for_bank_transfer_text(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []
    window = FakeControl("Create", "Window")
    document = FakeControl("Create document", "Document")

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._find_contains = lambda root, **kwargs: ClickTrackingControl("Управление способами оплаты", "Button", clicked) if "способами оплаты" in kwargs["text_part"].lower() else ClickTrackingControl("Подтвердить", "Button", clicked)  # type: ignore[method-assign]
    driver._click_best = lambda control: clicked.append(control.window_text())  # type: ignore[method-assign]

    bank = ClickTrackingControl("Bank Transfer", "Text", clicked)
    attempts = {"count": 0}
    clock = {"now": 0.0}

    def fake_time() -> float:
        return clock["now"]

    def fake_sleep(seconds: float) -> None:
        clock["now"] += seconds

    def fake_items(root):
        if root is document:
            return []
        if root is window:
            attempts["count"] += 1
            if attempts["count"] < 3:
                return []
            return [bank]
        return []

    monkeypatch.setattr(driver, "_interactive_items", fake_items)
    monkeypatch.setattr(driver_module.time, "time", fake_time)
    monkeypatch.setattr(driver_module.time, "sleep", fake_sleep)

    driver.ensure_payment_methods(
        "Bybit",
        driver_module.PaymentMethodState(
            bank_transfer=True,
            mobile_top_up=False,
            cash_deposit=False,
        ),
    )

    assert clicked == [
        "Управление способами оплаты",
        "Bank Transfer",
        "Подтвердить",
    ]
    assert attempts["count"] == 3


def test_ensure_payment_methods_opens_popup_via_safe_click(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []
    window = FakeControl("Create", "Window")
    document = FakeControl("Create document", "Document")

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._find_contains = lambda root, **kwargs: ClickTrackingControl("Управление способами оплаты", "Button", clicked) if "способами оплаты" in kwargs["text_part"].lower() else ClickTrackingControl("Подтвердить", "Button", clicked)  # type: ignore[method-assign]
    driver._set_checkbox_state = lambda control, checked: None  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    opener_clicked: list[str] = []
    driver._click_best = lambda control: opener_clicked.append(control.window_text())  # type: ignore[method-assign]

    bank = ClickTrackingControl("Bank Transfer", "Text", clicked)

    def fake_items(root):
        if root is document:
            return []
        if root is window:
            return [bank]
        return []

    monkeypatch.setattr(driver, "_interactive_items", fake_items)

    driver.ensure_payment_methods(
        "Bybit",
        driver_module.PaymentMethodState(
            bank_transfer=True,
            mobile_top_up=False,
            cash_deposit=False,
        ),
    )

    assert opener_clicked == [
        "Управление способами оплаты",
        "Bank Transfer",
        "Подтвердить",
    ]


def test_read_current_advertisement_extracts_snapshot_from_ads_listing() -> None:
    driver = ExistingBrowserWindowDriver()
    document = FakeControl(
        "Мои объявления",
        "Document",
        descendants=[
            FakeControl("Покупка USDT", "Text"),
            FakeControl("2026-07-04 22:19:47", "Text"),
            FakeControl("2072529315394842624", "Text"),
            FakeControl("80,00 RUB", "Text"),
        ],
    )
    window = FakeControl("Bybit", "Window", [document])
    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.ADS_URL  # type: ignore[method-assign]

    result = driver.read_current_advertisement("Bybit")

    assert result == AdvertisementSnapshot("2072529315394842624", "80,00", "Покупка", "2026-07-04 22:19:47")


def test_read_current_advertisement_finds_datetime_in_custom_element() -> None:
    driver = ExistingBrowserWindowDriver()
    document = FakeControl(
        "Мои объявления",
        "Document",
        descendants=[
            FakeControl("Покупка USDT", "Text"),
            FakeControl("2072529315394842624", "Text"),
            FakeControl("80,00 RUB", "Text"),
            FakeControl("2026-07-04 22:19:47", "Custom"),
        ],
    )
    window = FakeControl("Bybit", "Window", [document])
    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.ADS_URL  # type: ignore[method-assign]

    result = driver.read_current_advertisement("Bybit")

    assert result == AdvertisementSnapshot("2072529315394842624", "80,00", "Покупка", "2026-07-04 22:19:47")


def test_search_merchant_returns_page_and_position_for_normalized_match(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    current_page = {"value": 1}
    clicked_pages: list[str] = []
    window = FakeControl("Bybit", "Window")

    class PageControl(ClickTrackingControl):
        def invoke(self) -> None:
            clicked_pages.append(self.window_text())
            current_page["value"] = int(self.window_text())

    pages = {
        1: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Pakpakly", "Text"),
            FakeControl("Milano", "Text"),
            PageControl("1", "Button", clicked_pages),
            PageControl("2", "Button", clicked_pages),
        ],
        2: [
            FakeControl("Мерчант", "Text"),
            FakeControl("BubbleTea", "Text"),
            FakeControl(" Mannequin ✅ ", "Text"),
            PageControl("1", "Button", clicked_pages),
            PageControl("2", "Button", clicked_pages),
        ],
    }

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver._find_main_document = lambda _: FakeControl("Sell", "Document", descendants=pages[current_page["value"]])  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    def fake_find_exact(root, **kwargs):
        title = kwargs["title"]
        if title in {"1", "2"}:
            class _PageControl(ClickTrackingControl):
                def invoke(self_inner) -> None:
                    clicked_pages.append(title)
                    current_page["value"] = int(title)

            return _PageControl(title, "Button", clicked_pages)
        raise RuntimeError("Не найден элемент")

    driver._find_exact = fake_find_exact  # type: ignore[method-assign]

    progress: list[tuple[int, int, str]] = []
    result = driver.search_merchant(
        "Bybit",
        "mannequin",
        4,
        stop_requested=lambda: False,
        on_progress=lambda page, position, status: progress.append((page, position, status)),
    )

    assert result == MerchantSearchResult(found=True, page=2, position=2, matched_name="Mannequin")
    assert clicked_pages == ["1", "2"]
    assert progress[-1] == (2, 2, "Найден")


def test_search_merchant_ignores_intro_text_before_first_merchant_with_real_russian_dom(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    window = FakeControl("Bybit", "Window")
    document = FakeControl(
        "Sell",
        "Document",
        descendants=[
            FakeControl("\u041c\u0435\u0440\u0447\u0430\u043d\u0442", "Text"),
            FakeControl(
                "\u0412 \u0441\u043f\u0438\u0441\u043a\u0435 \u043d\u0438\u0436\u0435 \u043f\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u044b P2P-\u043f\u0440\u043e\u0432\u0430\u0439\u0434\u0435\u0440\u044b \u0432\u0430\u0448\u0435\u0433\u043e \u0440\u0435\u0433\u0438\u043e\u043d\u0430",
                "Text",
            ),
            FakeControl("Pakpakly", "Text"),
            FakeControl("Milano", "Text"),
        ],
    )

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    result = driver.search_merchant(
        "Bybit",
        "milano",
        1,
        stop_requested=lambda: False,
        on_progress=lambda *_: None,
    )

    assert result == MerchantSearchResult(found=True, page=1, position=2, matched_name="Milano")


def test_search_merchant_starts_from_first_page_with_real_russian_dom(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    current_page = {"value": 4}
    clicked_pages: list[str] = []
    window = FakeControl("Bybit", "Window")

    class PageControl(ClickTrackingControl):
        def invoke(self) -> None:
            clicked_pages.append(self.window_text())
            current_page["value"] = int(self.window_text())

    pages = {
        1: [
            FakeControl("\u041c\u0435\u0440\u0447\u0430\u043d\u0442", "Text"),
            FakeControl("Pakpakly", "Text"),
            PageControl("1", "Button", clicked_pages),
            PageControl("4", "Button", clicked_pages),
        ],
        4: [
            FakeControl("\u041c\u0435\u0440\u0447\u0430\u043d\u0442", "Text"),
            FakeControl("Milano", "Text"),
            PageControl("1", "Button", clicked_pages),
            PageControl("4", "Button", clicked_pages),
        ],
    }

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver._find_main_document = lambda _: FakeControl("Sell", "Document", descendants=pages[current_page["value"]])  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    def fake_find_exact(root, **kwargs):
        title = kwargs["title"]
        if title in {"1", "4"}:
            class _PageControl(ClickTrackingControl):
                def invoke(self_inner) -> None:
                    clicked_pages.append(title)
                    current_page["value"] = int(title)

            return _PageControl(title, "Button", clicked_pages)
        raise RuntimeError("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u044d\u043b\u0435\u043c\u0435\u043d\u0442")

    driver._find_exact = fake_find_exact  # type: ignore[method-assign]

    result = driver.search_merchant(
        "Bybit",
        "pakpakly",
        1,
        stop_requested=lambda: False,
        on_progress=lambda *_: None,
    )

    assert result == MerchantSearchResult(found=True, page=1, position=1, matched_name="Pakpakly")
    assert clicked_pages == ["1"]


def test_search_merchant_clicks_pagination_list_items(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    current_page = {"value": 1}
    clicked_pages: list[str] = []

    class PageControl(ClickTrackingControl):
        def invoke(self) -> None:
            clicked_pages.append(self.window_text())
            current_page["value"] = int(self.window_text())

    window = FakeControl("Bybit", "Window")
    pages = {
        1: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Pakpakly", "Text"),
            PageControl("1", "ListItem", clicked_pages),
            PageControl("2", "ListItem", clicked_pages),
        ],
        2: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Milano", "Text"),
            PageControl("1", "ListItem", clicked_pages),
            PageControl("2", "ListItem", clicked_pages),
        ],
    }

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver._find_main_document = lambda _: FakeControl("Sell", "Document", descendants=pages[current_page["value"]])  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    result = driver.search_merchant(
        "Bybit",
        "milano",
        2,
        stop_requested=lambda: False,
        on_progress=lambda *_: None,
    )

    assert result == MerchantSearchResult(found=True, page=2, position=1, matched_name="Milano")
    assert clicked_pages == ["1", "2"]


def test_search_merchant_reports_page_merchant_list_before_moving_next(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    current_page = {"value": 1}
    clicked_pages: list[str] = []
    window = FakeControl("Bybit", "Window")

    class PageControl(ClickTrackingControl):
        def invoke(self) -> None:
            clicked_pages.append(self.window_text())
            current_page["value"] = int(self.window_text())

    pages = {
        1: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Pakpakly", "Text"),
            FakeControl("Milano", "Text"),
            PageControl("1", "ListItem", clicked_pages),
            PageControl("2", "ListItem", clicked_pages),
        ],
        2: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Mannequin", "Text"),
            PageControl("1", "ListItem", clicked_pages),
            PageControl("2", "ListItem", clicked_pages),
        ],
    }

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver._find_main_document = lambda _: FakeControl("Sell", "Document", descendants=pages[current_page["value"]])  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    progress: list[tuple[int, int, str]] = []
    result = driver.search_merchant(
        "Bybit",
        "mannequin",
        2,
        stop_requested=lambda: False,
        on_progress=lambda page, position, status: progress.append((page, position, status)),
    )

    assert result == MerchantSearchResult(found=True, page=2, position=1, matched_name="Mannequin")
    assert (1, 0, "Страница 1, список мерчантов: Pakpakly, Milano") in progress
    assert (1, 0, "Никнейм 'mannequin' не найден на странице 1. Перехожу к следующей странице.") in progress


def test_delete_current_advertisement_does_not_click_unrelated_buttons_when_delete_is_missing() -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []

    class UnrelatedButton(ClickTrackingControl):
        def invoke(self) -> None:
            clicked.append(self.window_text())

    document = FakeControl(
        "My ads",
        "Document",
        descendants=[
            UnrelatedButton("Все объявления", "Button", clicked),
            UnrelatedButton("FAQ", "Button", clicked),
        ],
    )
    window = FakeControl("Bybit", "Window", [document])
    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.ADS_URL  # type: ignore[method-assign]

    driver.delete_current_advertisement("Bybit")


def test_search_merchant_does_not_click_faq_page_like_controls(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []

    class FaqButton(ClickTrackingControl):
        def invoke(self) -> None:
            clicked.append(self.window_text())

    document = FakeControl(
        "Sell",
        "Document",
        descendants=[
            FakeControl("Мерчант", "Text"),
            FakeControl("Pakpakly", "Text"),
            FakeControl("FAQ", "Text"),
            FaqButton("2", "Button", clicked),
        ],
    )
    window = FakeControl("Bybit", "Window", [document, FaqButton("2", "Button", clicked)])

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    try:
        driver.search_merchant(
            "Bybit",
            "milano",
            2,
            stop_requested=lambda: False,
            on_progress=lambda *_: None,
        )
    except RuntimeError as error:
        assert "2" in str(error)
    else:
        raise AssertionError("expected RuntimeError")


def test_select_trade_side_clicks_text_fallback_inside_toggle_group(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []
    choice = FakeControl("Покупка", "Text")
    document = FakeControl(
        "Create",
        "Document",
        descendants=[
            FakeControl("Покупка", "Text"),
            choice,
            FakeControl("Продажа", "Text"),
        ],
    )

    driver._find_window = lambda _: FakeControl("Bybit", "Window")  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._click_best = lambda control, **kwargs: clicked.append(control.window_text())  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.select_trade_side("Bybit", "Покупка")

    assert clicked == ["Покупка"]


def test_select_trade_side_skips_inert_text_and_verifies_buy_side_selected(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []
    summary = FakeControl("Продажа USDT", "Text")

    class InertChoice(ClickTrackingControl):
        def click_input(self) -> None:
            self._clicked.append("inert:" + self.window_text())

    class WorkingChoice(ClickTrackingControl):
        def click_input(self) -> None:
            self._clicked.append("active:" + self.window_text())
            summary._title = "Покупка USDT"

    inert = InertChoice("Покупка", "Text", clicked)
    working = WorkingChoice("Покупка", "Text", clicked)
    document = FakeControl(
        "Create",
        "Document",
        descendants=[
            summary,
            inert,
            working,
            FakeControl("Продажа", "Text"),
        ],
    )

    driver._find_window = lambda _: FakeControl("Bybit", "Window")  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._click_best = lambda control, **kwargs: control.click_input()  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.select_trade_side("Bybit", "Покупка")

    assert clicked == ["inert:Покупка", "active:Покупка"]
    assert summary.window_text() == "Покупка USDT"



def test_select_trade_side_moves_past_inert_choice_without_two_second_stall(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []
    summary = FakeControl("Продажа USDT", "Text")

    class InertChoice(ClickTrackingControl):
        def click_input(self) -> None:
            self._clicked.append("inert:" + self.window_text())

    class WorkingChoice(ClickTrackingControl):
        def click_input(self) -> None:
            self._clicked.append("active:" + self.window_text())
            summary._title = "Покупка USDT"

    inert = InertChoice("Покупка", "Text", clicked)
    working = WorkingChoice("Покупка", "Text", clicked)
    document = FakeControl(
        "Create",
        "Document",
        descendants=[
            summary,
            inert,
            working,
            FakeControl("Продажа", "Text"),
        ],
    )

    clock = {"now": 0.0}
    sleeps: list[float] = []

    def fake_time() -> float:
        return clock["now"]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    driver._find_window = lambda _: FakeControl("Bybit", "Window")  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._click_best = lambda control, **kwargs: control.click_input()  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "time", fake_time)
    monkeypatch.setattr(driver_module.time, "sleep", fake_sleep)

    driver.select_trade_side("Bybit", "Покупка")

    assert clicked == ["inert:Покупка", "active:Покупка"]
    assert sum(sleeps) < 1.0


def test_select_trade_side_reuses_initial_items_snapshot(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []
    summary = FakeControl("Продажа USDT", "Text")

    class WorkingChoice(ClickTrackingControl):
        def click_input(self) -> None:
            self._clicked.append(self.window_text())
            summary._title = "Покупка USDT"

    choice = WorkingChoice("Покупка", "Text", clicked)
    document = FakeControl(
        "Create",
        "Document",
        descendants=[
            summary,
            choice,
            FakeControl("Продажа", "Text"),
        ],
    )
    scan_count = {"count": 0}

    def fake_interactive_items(root):
        assert root is document
        scan_count["count"] += 1
        return document.descendants()

    driver._find_window = lambda _: FakeControl("Bybit", "Window")  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._click_best = lambda control, **kwargs: control.click_input()  # type: ignore[method-assign]
    monkeypatch.setattr(driver, "_interactive_items", fake_interactive_items)
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.select_trade_side("Bybit", "Покупка")

    assert clicked == ["Покупка"]
    assert scan_count["count"] <= 3


def test_select_trade_side_uses_single_final_scan_after_inert_candidates(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []
    summary = FakeControl("Продажа USDT", "Text")

    class InertChoice(ClickTrackingControl):
        def click_input(self) -> None:
            self._clicked.append("inert:" + self.window_text())

    class WorkingChoice(ClickTrackingControl):
        def click_input(self) -> None:
            self._clicked.append("active:" + self.window_text())
            summary._title = "Покупка USDT"

    document = FakeControl(
        "Create",
        "Document",
        descendants=[
            summary,
            InertChoice("Покупка", "Text", clicked),
            InertChoice("Покупка", "Text", clicked),
            WorkingChoice("Покупка", "Text", clicked),
            FakeControl("Продажа", "Text"),
        ],
    )
    scan_count = {"count": 0}

    def fake_interactive_items(root):
        assert root is document
        scan_count["count"] += 1
        return document.descendants()

    driver._find_window = lambda _: FakeControl("Bybit", "Window")  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._click_best = lambda control, **kwargs: control.click_input()  # type: ignore[method-assign]
    monkeypatch.setattr(driver, "_interactive_items", fake_interactive_items)
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver.select_trade_side("Bybit", "Покупка")

    assert clicked == ["inert:Покупка", "inert:Покупка", "active:Покупка"]
    assert scan_count["count"] <= 3


def test_ensure_payment_methods_uses_single_popup_scan_for_visible_cards(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []
    window = FakeControl("Create", "Window")
    document = FakeControl("Create document", "Document")

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    driver._find_contains = lambda root, **kwargs: ClickTrackingControl("Управление способами оплаты", "Button", clicked) if "способами оплаты" in kwargs["text_part"].lower() else ClickTrackingControl("Подтвердить", "Button", clicked)  # type: ignore[method-assign]
    driver._click_best = lambda control: clicked.append(control.window_text())  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    bank = ClickTrackingControl("Bank Transfer", "Text", clicked)
    mobile = ClickTrackingControl("Mobile Top-up", "Text", clicked)
    cash = ClickTrackingControl("Cash Deposit to Bank", "Text", clicked)
    popup_scan_count = {"window": 0}

    def fake_items(root):
        if root is document:
            return []
        if root is window:
            popup_scan_count["window"] += 1
            return [bank, mobile, cash]
        return []

    monkeypatch.setattr(driver, "_interactive_items", fake_items)

    def forbidden_find_exact(*_args, **_kwargs):
        raise AssertionError("visible popup cards should be reused from a single scan")

    driver._find_exact = forbidden_find_exact  # type: ignore[method-assign]

    driver.ensure_payment_methods(
        "Bybit",
        driver_module.PaymentMethodState(
            bank_transfer=True,
            mobile_top_up=True,
            cash_deposit=True,
        ),
    )

    assert clicked == [
        "Управление способами оплаты",
        "Bank Transfer",
        "Mobile Top-up",
        "Cash Deposit to Bank",
        "Подтвердить",
    ]
    assert popup_scan_count["window"] == 1


def test_search_merchant_does_not_click_text_page_controls_with_keyboard_fallback(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []

    class TextPage(FakeControl):
        def invoke(self) -> None:
            raise RuntimeError("text cannot invoke")

        @property
        def iface_invoke(self):
            class _Invoke:
                @staticmethod
                def Invoke() -> None:
                    raise RuntimeError("text cannot invoke")

            return _Invoke()

        def set_focus(self) -> None:
            clicked.append(f"focus:{self.window_text()}")

    document = FakeControl(
        "Sell",
        "Document",
        descendants=[
            FakeControl("Мерчант", "Text"),
            FakeControl("Pakpakly", "Text"),
            TextPage("2", "Text"),
        ],
    )
    window = FakeControl("Bybit", "Window", [document])
    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(driver_module, "send_keys", lambda keys, **kwargs: clicked.append(f"keys:{keys}"))

    try:
        driver.search_merchant(
            "Bybit",
            "milano",
            2,
            stop_requested=lambda: False,
            on_progress=lambda *_: None,
        )
    except RuntimeError as error:
        assert "2" in str(error)
    else:
        raise AssertionError("expected RuntimeError")

    assert clicked == []


def test_search_merchant_stops_page_lookup_before_buy_sell_coin_block(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    clicked: list[str] = []

    class MarketingButton(ClickTrackingControl):
        def invoke(self) -> None:
            clicked.append(self.window_text())

    document = FakeControl(
        "Sell",
        "Document",
        descendants=[
            FakeControl("Мерчант", "Text"),
            FakeControl("Pakpakly", "Text"),
            FakeControl("Купить монеты", "Button"),
            MarketingButton("2", "Button", clicked),
            FakeControl("Продать монеты", "Button"),
        ],
    )
    window = FakeControl("Bybit", "Window", [document])
    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver._find_main_document = lambda _: document  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    try:
        driver.search_merchant(
            "Bybit",
            "milano",
            2,
            stop_requested=lambda: False,
            on_progress=lambda *_: None,
        )
    except RuntimeError as error:
        assert "2" in str(error)
    else:
        raise AssertionError("expected RuntimeError")

    assert clicked == []


def test_extract_merchant_candidates_reads_first_page_merchant_names_from_real_data_items() -> None:
    driver = ExistingBrowserWindowDriver()
    document = FakeControl(
        "Sell",
        "Document",
        descendants=[
            FakeControl("Мерчант", "DataItem"),
            FakeControl("Цена", "DataItem"),
            FakeControl("Доступно|Лимиты", "DataItem"),
            FakeControl("Способ оплаты", "DataItem"),
            FakeControl("Taker 0 Transaction Fees", "DataItem"),
            FakeControl(
                "В списке ниже представлены P2P-провайдеры вашего региона. (Сбербанк/Газпромбанк/Альфа-банк/Банк Открытие/Банк ВТБ/СБП/МИР)",
                "DataItem",
            ),
            FakeControl("P Pakpakly💎 219 исполнено | 100 % | 1мин. Быстрая оплата", "DataItem"),
            FakeControl("77,56 RUB", "DataItem"),
            FakeControl("69 277,3518 USDT 10 000,00 ~ 3 500 000,00 RUB", "DataItem"),
            FakeControl("Cash Deposit to Bank Mobile Top-up Bank Transfer", "DataItem"),
            FakeControl("Продать USDT", "DataItem"),
            FakeControl("S Sarmat) 254 исполнено | 100 % | 2мин. Быстрая оплата", "DataItem"),
            FakeControl("77,56 RUB", "DataItem"),
            FakeControl("92 075,7071 USDT 20 000,00 ~ 3 500 000,00 RUB", "DataItem"),
            FakeControl("Cash Deposit to Bank Mobile Top-up Наличные", "DataItem"),
            FakeControl("Продать USDT", "DataItem"),
            FakeControl("H hatessl 577 исполнено | 100 % | 1мин. Быстрая оплата", "DataItem"),
            FakeControl("77,56 RUB", "DataItem"),
            FakeControl("57 918,5742 USDT 10 000,00 ~ 3 500 000,00 RUB", "DataItem"),
            FakeControl("Cash Deposit to Bank Mobile Top-up Наличные", "DataItem"),
            FakeControl("Продать USDT", "DataItem"),
            FakeControl("🏧 🏧ATM🏧 753 исполнено | 100 % | 1мин. Быстрая оплата", "DataItem"),
            FakeControl("77,56 RUB", "DataItem"),
            FakeControl("66 000,0000 USDT 25 000,00 ~ 3 500 000,00 RUB", "DataItem"),
            FakeControl("Mobile Top-up Bank Transfer", "DataItem"),
            FakeControl("Продать USDT", "DataItem"),
            FakeControl("M MonteCristo💴 730 исполнено | 100 % | 1мин. Быстрая оплата", "DataItem"),
            FakeControl("77,56 RUB", "DataItem"),
            FakeControl("52 223,0885 USDT 10 000,00 ~ 3 500 000,00 RUB", "DataItem"),
            FakeControl("Cash Deposit to Bank Mobile Top-up Bank Transfer", "DataItem"),
            FakeControl("Продать USDT", "DataItem"),
            FakeControl("P Pakpakly💎 219 исполнено | 100 % | 1мин. Быстрая оплата", "DataItem"),
            FakeControl("77,56 RUB", "DataItem"),
            FakeControl("70 531,4732 USDT 20 000,00 ~ 3 500 000,00 RUB", "DataItem"),
            FakeControl("Cash Deposit to Bank Mobile Top-up Bank Transfer", "DataItem"),
            FakeControl("Продать USDT", "DataItem"),
            FakeControl("T Teacher_pro 593 исполнено | 100 % | 2мин. Быстрая оплата", "DataItem"),
            FakeControl("77,56 RUB", "DataItem"),
            FakeControl("65 665,0164 USDT 5000,00 ~ 3 500 000,00 RUB", "DataItem"),
            FakeControl("Cash Deposit to Bank Bank Transfer", "DataItem"),
            FakeControl("Продать USDT", "DataItem"),
            FakeControl("🎷 🎷КриптоJazz 233 исполнено | 100 % | 1мин. Быстрая оплата", "DataItem"),
            FakeControl("77,56 RUB", "DataItem"),
            FakeControl("86 765,0734 USDT 10 000,00 ~ 3 500 000,00 RUB", "DataItem"),
            FakeControl("Cash Deposit to Bank Mobile Top-up Наличные", "DataItem"),
            FakeControl("Продать USDT", "DataItem"),
            FakeControl("💸 💸Garant💸 578 исполнено | 100 % | 2мин. Быстрая оплата", "DataItem"),
            FakeControl("77,56 RUB", "DataItem"),
            FakeControl("99 789,6188 USDT 4000,00 ~ 3 500 000,00 RUB", "DataItem"),
            FakeControl("Cash Deposit to Bank Mobile Top-up Bank Transfer", "DataItem"),
            FakeControl("Продать USDT", "DataItem"),
            FakeControl("S Sazon 255 исполнено | 100 % | 1мин. Быстрая оплата", "DataItem"),
            FakeControl("77,56 RUB", "DataItem"),
            FakeControl("90 753,3113 USDT 5000,00 ~ 3 500 000,00 RUB", "DataItem"),
            FakeControl("Cash Deposit to Bank Mobile Top-up Наличные", "DataItem"),
            FakeControl("Продать USDT", "DataItem"),
            FakeControl("‹", "ListItem"),
            FakeControl("prev page", "Button"),
            FakeControl("1", "ListItem"),
            FakeControl("2", "ListItem"),
            FakeControl("3", "ListItem"),
            FakeControl("4", "ListItem"),
            FakeControl("5", "ListItem"),
            FakeControl("Продайте USDT за RUB в три простых шага", "Text"),
        ],
    )

    result = driver._extract_merchant_candidates(document)

    assert result == [
        "Pakpakly",
        "Sarmat",
        "hatessl",
        "ATM",
        "MonteCristo",
        "Pakpakly",
        "Teacher_pro",
        "КриптоJazz",
        "Garant",
        "Sazon",
    ]


def test_collect_all_merchants_starts_from_first_page_before_collecting(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    current_page = {"value": 4}
    clicked_pages: list[str] = []
    opened_urls: list[str] = []
    window = FakeControl("Bybit", "Window")

    class PageControl(ClickTrackingControl):
        def invoke(self) -> None:
            clicked_pages.append(self.window_text())
            current_page["value"] = int(self.window_text())

    pages = {
        1: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Pakpakly", "Text"),
            FakeControl("Milano", "Text"),
            PageControl("1", "ListItem", clicked_pages),
            PageControl("2", "ListItem", clicked_pages),
            PageControl("4", "ListItem", clicked_pages),
        ],
        2: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Teacher_pro", "Text"),
            FakeControl("Garant", "Text"),
            PageControl("1", "ListItem", clicked_pages),
            PageControl("2", "ListItem", clicked_pages),
            PageControl("4", "ListItem", clicked_pages),
        ],
        4: [
            FakeControl("Мерчант", "Text"),
            FakeControl("WrongStart", "Text"),
            PageControl("1", "ListItem", clicked_pages),
            PageControl("2", "ListItem", clicked_pages),
            PageControl("4", "ListItem", clicked_pages),
        ],
    }

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    def fake_open_url(_window_title, url):
        opened_urls.append(url)
        current_page["value"] = 1

    driver.open_url = fake_open_url  # type: ignore[method-assign]
    driver._find_main_document = lambda _: FakeControl("Sell", "Document", descendants=pages[current_page["value"]])  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    merchants = driver.collect_all_merchants("Bybit", 2)

    assert merchants == ["Pakpakly", "Milano", "Teacher_pro", "Garant"]
    assert clicked_pages == ["2"]
    assert opened_urls == [driver.SELL_URL]


def test_collect_all_merchants_waits_for_next_page_content_before_collecting(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    current_page = {"value": 1}
    pending_page = {"value": None}
    pending_reads = {"value": 0}
    clicked_pages: list[str] = []
    window = FakeControl("Bybit", "Window")

    class PageControl(ClickTrackingControl):
        def __init__(self, title: str) -> None:
            super().__init__(title, "ListItem", clicked_pages)

        def invoke(self) -> None:
            clicked_pages.append(self.window_text())
            pending_page["value"] = int(self.window_text())
            pending_reads["value"] = 2

    pages = {
        1: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Pakpakly", "Text"),
            FakeControl("Milano", "Text"),
            PageControl("1"),
            PageControl("2"),
        ],
        2: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Teacher_pro", "Text"),
            FakeControl("Garant", "Text"),
            PageControl("1"),
            PageControl("2"),
        ],
    }

    def fake_document(_window):
        if pending_page["value"] is not None:
            if pending_reads["value"] > 0:
                pending_reads["value"] -= 1
            else:
                current_page["value"] = pending_page["value"]
                pending_page["value"] = None
        return FakeControl("Sell", "Document", descendants=pages[current_page["value"]])

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver.open_url = lambda *_: None  # type: ignore[method-assign]
    driver._find_main_document = fake_document  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    merchants = driver.collect_all_merchants("Bybit", 2)

    assert merchants == ["Pakpakly", "Milano", "Teacher_pro", "Garant"]
    assert clicked_pages == ["2"]


def test_read_current_sell_price_resets_scroll_to_top_before_scanning(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    events: list[str] = []
    window = FakeControl("Bybit", "Window")
    top_document = FakeControl(
        "Sell",
        "Document",
        descendants=[
            FakeControl("Цена", "Text"),
            FakeControl("77,29 RUB", "Text"),
        ],
    )
    bottom_document = FakeControl(
        "Sell",
        "Document",
        descendants=[
            FakeControl("FAQ", "Text"),
            FakeControl("Поддержка", "Text"),
        ],
    )
    state = {"at_top": False}

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver._find_document_by_title_part = lambda *_: top_document if state["at_top"] else bottom_document  # type: ignore[method-assign]
    driver.focus = lambda window_title: events.append(f"focus:{window_title}")  # type: ignore[method-assign]

    def fake_send_keys(keys, **kwargs):
        events.append(f"keys:{keys}")
        if keys == "{HOME}":
            state["at_top"] = True

    monkeypatch.setattr(driver_module, "send_keys", fake_send_keys)
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    result = driver.read_current_sell_price("Bybit")

    assert result == "77,29"
    assert "keys:{HOME}" in events


def test_click_best_does_not_log_regular_success_path(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    logs: list[str] = []

    class LocalLogger:
        def info(self, message: str) -> None:
            logs.append(message)

    driver._logger = LocalLogger()
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    driver._click_best(FakeControl("Обычная кнопка", "Button"))

    assert logs == []


def test_search_merchant_waits_for_new_page_candidates_before_matching(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    current_page = {"value": 1}
    pending_page = {"value": None}
    pending_reads = {"value": 0}
    clicked_pages: list[str] = []
    window = FakeControl("Bybit", "Window")

    class PageControl(ClickTrackingControl):
        def __init__(self, title: str) -> None:
            super().__init__(title, "ListItem", clicked_pages)

        def invoke(self) -> None:
            clicked_pages.append(self.window_text())
            if self.window_text() == "1":
                current_page["value"] = 1
                pending_page["value"] = None
                pending_reads["value"] = 0
                return
            pending_page["value"] = int(self.window_text())
            pending_reads["value"] = 2

    pages = {
        1: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Pakpakly", "Text"),
            PageControl("1"),
            PageControl("2"),
        ],
        2: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Milano", "Text"),
            PageControl("1"),
            PageControl("2"),
        ],
    }

    def fake_document(_window):
        if pending_page["value"] is not None:
            if pending_reads["value"] > 0:
                pending_reads["value"] -= 1
            else:
                current_page["value"] = pending_page["value"]
                pending_page["value"] = None
        return FakeControl("Sell", "Document", descendants=pages[current_page["value"]])

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver._find_main_document = fake_document  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    result = driver.search_merchant(
        "Bybit",
        "milano",
        2,
        stop_requested=lambda: False,
        on_progress=lambda *_: None,
    )

    assert result == MerchantSearchResult(found=True, page=2, position=1, matched_name="Milano")
    assert clicked_pages == ["1", "2"]


def test_collect_all_merchants_does_not_reclick_first_page_after_open_url(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    current_page = {"value": 1}
    clicked_pages: list[str] = []
    opened_urls: list[str] = []
    window = FakeControl("Bybit", "Window")

    class PageControl(ClickTrackingControl):
        def __init__(self, title: str) -> None:
            super().__init__(title, "ListItem", clicked_pages)

        def invoke(self) -> None:
            clicked_pages.append(self.window_text())
            current_page["value"] = int(self.window_text())

    pages = {
        1: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Pakpakly", "Text"),
            FakeControl("Milano", "Text"),
            PageControl("1"),
            PageControl("2"),
        ],
        2: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Teacher_pro", "Text"),
            FakeControl("Garant", "Text"),
            PageControl("1"),
            PageControl("2"),
        ],
    }

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver.open_url = lambda _, url: opened_urls.append(url)  # type: ignore[method-assign]
    driver._find_main_document = lambda _: FakeControl("Sell", "Document", descendants=pages[current_page["value"]])  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    merchants = driver.collect_all_merchants("Bybit", 2)

    assert merchants == ["Pakpakly", "Milano", "Teacher_pro", "Garant"]
    assert clicked_pages == ["2"]
    assert opened_urls == [driver.SELL_URL]


def test_collect_all_merchants_waits_for_pagination_before_collecting(monkeypatch) -> None:
    driver = ExistingBrowserWindowDriver()
    reads = {"value": 0}
    current_page = {"value": 1}
    clicked_pages: list[str] = []
    window = FakeControl("Bybit", "Window")

    class PageControl(ClickTrackingControl):
        def __init__(self, title: str) -> None:
            super().__init__(title, "ListItem", clicked_pages)

        def invoke(self) -> None:
            clicked_pages.append(self.window_text())
            current_page["value"] = int(self.window_text())

    page_one_without_pagination = [
        FakeControl("Мерчант", "Text"),
        FakeControl("WrongEarly", "Text"),
    ]
    pages = {
        1: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Pakpakly", "Text"),
            FakeControl("Milano", "Text"),
            PageControl("1"),
            PageControl("2"),
        ],
        2: [
            FakeControl("Мерчант", "Text"),
            FakeControl("Teacher_pro", "Text"),
            FakeControl("Garant", "Text"),
            PageControl("1"),
            PageControl("2"),
        ],
    }

    def fake_document(_window):
        if current_page["value"] == 1:
            reads["value"] += 1
            if reads["value"] == 1:
                return FakeControl("Sell", "Document", descendants=page_one_without_pagination)
        return FakeControl("Sell", "Document", descendants=pages[current_page["value"]])

    driver._find_window = lambda _: window  # type: ignore[method-assign]
    driver._read_current_url = lambda _: driver.SELL_URL  # type: ignore[method-assign]
    driver.open_url = lambda *_: None  # type: ignore[method-assign]
    driver._find_main_document = fake_document  # type: ignore[method-assign]
    monkeypatch.setattr(driver_module.time, "sleep", lambda _: None)

    merchants = driver.collect_all_merchants("Bybit", 2)

    assert merchants == ["Pakpakly", "Milano", "Teacher_pro", "Garant"]
    assert clicked_pages == ["2"]
    assert reads["value"] >= 2
