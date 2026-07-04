from __future__ import annotations

from bybit_automation.models.app_state import AppState
from bybit_automation.models.merchant_cycle import AdvertisementSnapshot, MerchantSearchResult
from bybit_automation.services.bybit_existing_browser_service import BybitExistingBrowserService
from bybit_automation.services.logging_service import AppLogger


class FakeDriver:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.sell_price = "80,99"

    def focus(self, window_title: str) -> None:
        self.calls.append(("focus", window_title))

    def ensure_sell_tab(self, window_title: str) -> None:
        self.calls.append(("ensure_sell_tab", window_title))

    def refresh_page(self, window_title: str) -> None:
        self.calls.append(("refresh_page", window_title))

    def read_current_sell_price(self, window_title: str) -> str:
        self.calls.append(("read_current_sell_price", window_title))
        return self.sell_price

    def ensure_ads_tab(self, window_title: str) -> None:
        self.calls.append(("ensure_ads_tab", window_title))

    def open_standard_p2p_ad_form(self, window_title: str) -> None:
        self.calls.append(("open_standard_p2p_ad_form", window_title))

    def select_trade_side(self, window_title: str, trade_side: str) -> None:
        self.calls.append(("select_trade_side", window_title, trade_side))

    def set_fixed_price(self, window_title: str, price: str) -> None:
        self.calls.append(("set_fixed_price", window_title, price))

    def set_payment_time(self, window_title: str, payment_time: str) -> None:
        self.calls.append(("set_payment_time", window_title, payment_time))

    def set_total_amount(self, window_title: str, total_amount: str) -> None:
        self.calls.append(("set_total_amount", window_title, total_amount))

    def set_minimum_transaction(self, window_title: str, minimum_transaction: str) -> None:
        self.calls.append(("set_minimum_transaction", window_title, minimum_transaction))

    def set_maximum_transaction(self, window_title: str, maximum_transaction: str) -> None:
        self.calls.append(("set_maximum_transaction", window_title, maximum_transaction))

    def set_notes(self, window_title: str, notes: str) -> None:
        self.calls.append(("set_notes", window_title, notes))

    def ensure_counterparty_requirements(self, window_title: str, *, phone_linked: bool, email_linked: bool) -> None:
        self.calls.append(("ensure_counterparty_requirements", window_title, phone_linked, email_linked))

    def ensure_payment_methods(self, window_title: str, methods) -> None:
        self.calls.append(
            (
                "ensure_payment_methods",
                window_title,
                methods.bank_transfer,
                methods.mobile_top_up,
                methods.cash_deposit,
            )
        )

    def accept_terms(self, window_title: str) -> None:
        self.calls.append(("accept_terms", window_title))

    def submit_advertisement(self, window_title: str) -> None:
        self.calls.append(("submit_advertisement", window_title))

    def enter_security_password(self, window_title: str, password: str) -> None:
        self.calls.append(("enter_security_password", window_title, password))

    def sleep(self, seconds: float) -> None:
        self.calls.append(("sleep", seconds))

    def read_current_advertisement(self, window_title: str):
        self.calls.append(("read_current_advertisement", window_title))
        return AdvertisementSnapshot("ad-1", "81,31", "Покупка")

    def delete_current_advertisement(self, window_title: str) -> None:
        self.calls.append(("delete_current_advertisement", window_title))

    def search_merchant(self, window_title: str, account_name: str, depth: int, stop_requested, on_progress):
        self.calls.append(("search_merchant", window_title, account_name, depth))
        on_progress(2, 5, "Найден")
        return MerchantSearchResult(found=True, page=2, position=5)


def test_fill_form_returns_false_without_window_title() -> None:
    service = BybitExistingBrowserService(driver=FakeDriver(), logger=AppLogger())

    result = service.fill_advertisement_form(AppState())

    assert result is False


def test_fetch_current_price_uses_existing_sell_tab() -> None:
    driver = FakeDriver()
    service = BybitExistingBrowserService(driver=driver, logger=AppLogger())

    result = service.fetch_current_price("Buy crypto with currency via Bybit P2P Crypto Trading - ILYA BB - 1")

    assert result == "80,99"
    assert ("focus", "Buy crypto with currency via Bybit P2P Crypto Trading - ILYA BB - 1") in driver.calls
    assert ("ensure_sell_tab", "Buy crypto with currency via Bybit P2P Crypto Trading - ILYA BB - 1") in driver.calls
    assert ("refresh_page", "Buy crypto with currency via Bybit P2P Crypto Trading - ILYA BB - 1") in driver.calls
    assert ("read_current_sell_price", "Buy crypto with currency via Bybit P2P Crypto Trading - ILYA BB - 1") in driver.calls


def test_fill_form_runs_expected_sequence_for_existing_window() -> None:
    driver = FakeDriver()
    service = BybitExistingBrowserService(driver=driver, logger=AppLogger())
    state = AppState()
    state.browser.window_title = "Buy crypto with currency via Bybit P2P Crypto Trading - ILYA BB - 1"
    state.advertisement.trade_side = "Покупка"
    state.advertisement.fixed_price = "81,12"
    state.advertisement.payment_time = "30 минут"
    state.advertisement.total_amount = "20000"
    state.advertisement.minimum_transaction = "4000"
    state.advertisement.maximum_transaction = "3500000"
    state.advertisement.notes = "СБП, реквизиты в чат"
    state.advertisement.payment_cash_deposit = True
    state.advertisement.payment_mobile_top_up = True
    state.advertisement.payment_bank_transfer = True
    state.advertisement.security_password = "Salam1337$"

    result = service.fill_advertisement_form(state)

    assert result is True
    assert ("focus", state.browser.window_title) in driver.calls
    assert ("ensure_ads_tab", state.browser.window_title) in driver.calls
    assert ("open_standard_p2p_ad_form", state.browser.window_title) in driver.calls
    assert ("set_fixed_price", state.browser.window_title, "80,99") in driver.calls
    assert ("set_payment_time", state.browser.window_title, "30 минут") in driver.calls
    assert ("submit_advertisement", state.browser.window_title) in driver.calls
    assert ("enter_security_password", state.browser.window_title, "Salam1337$") in driver.calls


def test_fill_form_deletes_existing_advertisement_before_opening_form() -> None:
    driver = FakeDriver()
    service = BybitExistingBrowserService(driver=driver, logger=AppLogger())
    state = AppState()
    state.browser.window_title = "Bybit - ILYA BB - 1"

    result = service.fill_advertisement_form(state)

    assert result is True
    assert driver.calls.index(("ensure_sell_tab", state.browser.window_title)) < driver.calls.index(
        ("refresh_page", state.browser.window_title)
    )
    assert driver.calls.index(("refresh_page", state.browser.window_title)) < driver.calls.index(
        ("read_current_sell_price", state.browser.window_title)
    )
    assert driver.calls.index(("read_current_sell_price", state.browser.window_title)) < driver.calls.index(
        ("ensure_ads_tab", state.browser.window_title)
    )
    assert driver.calls.index(("read_current_advertisement", state.browser.window_title)) < driver.calls.index(
        ("delete_current_advertisement", state.browser.window_title)
    )
    assert driver.calls.index(("delete_current_advertisement", state.browser.window_title)) < driver.calls.index(
        ("open_standard_p2p_ad_form", state.browser.window_title)
    )


def test_fill_form_continues_when_no_existing_advertisement() -> None:
    class NoAdvertisementDriver(FakeDriver):
        def read_current_advertisement(self, window_title: str):
            self.calls.append(("read_current_advertisement", window_title))
            return None

    driver = NoAdvertisementDriver()
    service = BybitExistingBrowserService(driver=driver, logger=AppLogger())
    state = AppState()
    state.browser.window_title = "Bybit - ILYA BB - 1"

    result = service.fill_advertisement_form(state)

    assert result is True
    assert ("delete_current_advertisement", state.browser.window_title) not in driver.calls
    assert ("open_standard_p2p_ad_form", state.browser.window_title) in driver.calls


def test_fill_form_continues_when_delete_button_is_missing() -> None:
    class MissingDeleteButtonDriver(FakeDriver):
        def delete_current_advertisement(self, window_title: str) -> None:
            self.calls.append(("delete_current_advertisement", window_title))
            raise RuntimeError("Не удалось найти кнопку удаления объявления.")

    driver = MissingDeleteButtonDriver()
    service = BybitExistingBrowserService(driver=driver, logger=AppLogger())
    state = AppState()
    state.browser.window_title = "Bybit - ILYA BB - 1"

    result = service.fill_advertisement_form(state)

    assert result is True
    assert ("delete_current_advertisement", state.browser.window_title) in driver.calls
    assert ("open_standard_p2p_ad_form", state.browser.window_title) in driver.calls


def test_fill_form_uses_fresh_price_before_filling_fields() -> None:
    driver = FakeDriver()
    driver.sell_price = "82,45"
    service = BybitExistingBrowserService(driver=driver, logger=AppLogger())
    state = AppState()
    state.browser.window_title = "Bybit - ILYA BB - 1"
    state.advertisement.fixed_price = "80,00"

    result = service.fill_advertisement_form(state)

    assert result is True
    assert state.advertisement.fixed_price == "82,45"
    assert ("set_fixed_price", state.browser.window_title, "82,45") in driver.calls


def test_fill_form_stops_when_current_price_cannot_be_read() -> None:
    class BrokenPriceDriver(FakeDriver):
        def read_current_sell_price(self, window_title: str) -> str:
            self.calls.append(("read_current_sell_price", window_title))
            raise RuntimeError("Не удалось прочитать цену на первой вкладке.")

    driver = BrokenPriceDriver()
    logger = AppLogger()
    messages: list[str] = []
    logger.subscribe(messages.append)
    service = BybitExistingBrowserService(driver=driver, logger=logger)
    state = AppState()
    state.browser.window_title = "Bybit - ILYA BB - 1"

    try:
        service.fill_advertisement_form(state)
    except RuntimeError as error:
        assert "Не удалось подтянуть актуальную цену перед созданием объявления" in str(error)
        assert "Не удалось прочитать цену на первой вкладке." in str(error)
    else:
        raise AssertionError("expected RuntimeError")

    assert ("open_standard_p2p_ad_form", state.browser.window_title) not in driver.calls
    assert all(call[0] != "set_fixed_price" for call in driver.calls)
    assert any("Подтягиваю актуальную цену с первой вкладки" in message for message in messages)
    assert any("Не удалось подтянуть актуальную цену перед созданием объявления" in message for message in messages)


def test_fetch_current_price_works_with_russian_sell_tab_title() -> None:
    driver = FakeDriver()
    service = BybitExistingBrowserService(driver=driver, logger=AppLogger())
    window_title = "Продать USDT за RUB через криптотрейдинг на Bybit P2P - ILYA BB - 1"

    result = service.fetch_current_price(window_title)

    assert result == "80,99"
    assert ("focus", window_title) in driver.calls
    assert ("ensure_sell_tab", window_title) in driver.calls
    assert ("refresh_page", window_title) in driver.calls
    assert ("read_current_sell_price", window_title) in driver.calls


def test_gateway_reads_current_advertisement_from_ads_tab() -> None:
    driver = FakeDriver()
    service = BybitExistingBrowserService(driver=driver, logger=AppLogger())

    result = service.read_current_advertisement("Bybit - ILYA BB - 1")

    assert result == AdvertisementSnapshot("ad-1", "81,31", "Покупка")
    assert ("ensure_ads_tab", "Bybit - ILYA BB - 1") in driver.calls
    assert ("read_current_advertisement", "Bybit - ILYA BB - 1") in driver.calls


def test_gateway_search_merchant_uses_sell_tab() -> None:
    driver = FakeDriver()
    service = BybitExistingBrowserService(driver=driver, logger=AppLogger())
    progress: list[tuple[int, int, str]] = []

    result = service.search_merchant(
        "Bybit - ILYA BB - 1",
        "Mannequin",
        4,
        stop_requested=lambda: False,
        on_progress=lambda page, position, status: progress.append((page, position, status)),
    )

    assert result == MerchantSearchResult(found=True, page=2, position=5)
    assert ("ensure_sell_tab", "Bybit - ILYA BB - 1") in driver.calls
    assert ("search_merchant", "Bybit - ILYA BB - 1", "Mannequin", 4) in driver.calls
    assert progress == [(2, 5, "Найден")]


def test_create_advertisement_waits_until_created_ad_is_visible() -> None:
    class DelayedAdvertisementDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.read_attempts = 0

        def read_current_advertisement(self, window_title: str):
            self.calls.append(("read_current_advertisement", window_title))
            self.read_attempts += 1
            if self.read_attempts < 3:
                return None
            return AdvertisementSnapshot("ad-3", "81,31", "Покупка")

    driver = DelayedAdvertisementDriver()
    logger = AppLogger()
    messages: list[str] = []
    logger.subscribe(messages.append)
    service = BybitExistingBrowserService(driver=driver, logger=logger)
    state = AppState()
    state.browser.window_title = "Bybit - ILYA BB - 1"

    result = service.create_advertisement(state)

    assert result == AdvertisementSnapshot("ad-3", "81,31", "Покупка")
    assert driver.read_attempts == 3
    assert any("Ожидаю появления созданного объявления" in message for message in messages)


def test_create_advertisement_raises_clear_error_when_created_ad_does_not_appear() -> None:
    class MissingAdvertisementDriver(FakeDriver):
        def read_current_advertisement(self, window_title: str):
            self.calls.append(("read_current_advertisement", window_title))
            return None

    driver = MissingAdvertisementDriver()
    logger = AppLogger()
    messages: list[str] = []
    logger.subscribe(messages.append)
    service = BybitExistingBrowserService(driver=driver, logger=logger)
    state = AppState()
    state.browser.window_title = "Bybit - ILYA BB - 1"

    try:
        service.create_advertisement(state)
    except RuntimeError as error:
        assert "Не удалось дождаться появления созданного объявления" in str(error)
    else:
        raise AssertionError("expected RuntimeError")

    assert any("Не удалось дождаться появления созданного объявления" in message for message in messages)


def test_collect_all_merchants_retries_after_transient_failure_and_returns_result() -> None:
    class FlakyCollectDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.collect_attempts = 0

        def collect_all_merchants(self, window_title: str, depth: int):
            self.calls.append(("collect_all_merchants", window_title, depth))
            self.collect_attempts += 1
            if self.collect_attempts == 1:
                raise RuntimeError(None)
            return ["Alpha", "Beta"]

    driver = FlakyCollectDriver()
    logger = AppLogger()
    messages: list[str] = []
    logger.subscribe(messages.append)
    service = BybitExistingBrowserService(driver=driver, logger=logger)

    merchants = service.collect_all_merchants("Bybit - ILYA BB - 1", 2)

    assert merchants == ["Alpha", "Beta"]
    assert driver.collect_attempts == 2
    assert any("Сбой сбора мерчантов, повторяю попытку 1/3" in message for message in messages)


def test_collect_all_merchants_raises_clear_error_after_all_retries(tmp_path) -> None:
    class BrokenCollectDriver(FakeDriver):
        def collect_all_merchants(self, window_title: str, depth: int):
            self.calls.append(("collect_all_merchants", window_title, depth))
            raise RuntimeError(None)

    driver = BrokenCollectDriver()
    logger = AppLogger()
    messages: list[str] = []
    logger.subscribe(messages.append)
    service = BybitExistingBrowserService(driver=driver, logger=logger)

    try:
        service.collect_all_merchants("Bybit - ILYA BB - 1", 2)
    except RuntimeError as error:
        assert "Сбор мерчантов сорвался после 3 попыток" in str(error)
        assert "RuntimeError(None)" in str(error)
    else:
        raise AssertionError("expected RuntimeError")

    assert any("Сбор мерчантов сорвался после 3 попыток" in message for message in messages)


def test_collect_all_merchants_retries_when_ensure_sell_tab_temporarily_fails() -> None:
    class FlakySellTabDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.ensure_attempts = 0

        def ensure_sell_tab(self, window_title: str) -> None:
            self.calls.append(("ensure_sell_tab", window_title))
            self.ensure_attempts += 1
            if self.ensure_attempts == 1:
                raise KeyError(None)

        def collect_all_merchants(self, window_title: str, depth: int):
            self.calls.append(("collect_all_merchants", window_title, depth))
            return ["Alpha", "Beta"]

    driver = FlakySellTabDriver()
    logger = AppLogger()
    messages: list[str] = []
    logger.subscribe(messages.append)
    service = BybitExistingBrowserService(driver=driver, logger=logger)

    merchants = service.collect_all_merchants("Bybit - ILYA BB - 1", 2)

    assert merchants == ["Alpha", "Beta"]
    assert driver.ensure_attempts == 2
    assert any("повторяю попытку 1/3: KeyError(None)" in message for message in messages)


def test_create_advertisement_retries_when_read_current_advertisement_temporarily_raises_key_error() -> None:
    class FlakyCreatedAdDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.read_attempts = 0

        def read_current_advertisement(self, window_title: str):
            self.calls.append(("read_current_advertisement", window_title))
            self.read_attempts += 1
            if self.read_attempts == 1:
                raise KeyError(None)
            return AdvertisementSnapshot("ad-9", "81,31", "Покупка")

    driver = FlakyCreatedAdDriver()
    logger = AppLogger()
    messages: list[str] = []
    logger.subscribe(messages.append)
    service = BybitExistingBrowserService(driver=driver, logger=logger)
    state = AppState()
    state.browser.window_title = "Bybit - ILYA BB - 1"

    result = service.create_advertisement(state)

    assert result == AdvertisementSnapshot("ad-9", "81,31", "Покупка")
    assert driver.read_attempts >= 3
    assert any("KeyError(None)" in message for message in messages)
