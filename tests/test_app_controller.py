from __future__ import annotations

from pathlib import Path

from bybit_automation.controllers.app_controller import AppController
from bybit_automation.models.merchant_cycle import AdvertisementSnapshot, MerchantSearchResult
from bybit_automation.services.browser_discovery_service import BrowserDiscoveryService
from bybit_automation.services.bybit_existing_browser_service import BybitExistingBrowserService
from bybit_automation.services.logging_service import AppLogger
from bybit_automation.services.merchant_cycle_service import MerchantCycleService
from bybit_automation.services.settings_service import JsonSettingsService


def test_reset_returns_default_state(tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())

    state = controller.reset_settings()

    assert state.advertisement.fixed_price == "80"
    assert state.advertisement.trade_side == "Покупка"
    assert state.browser.browser_name == "Incogniton"


def test_placeholder_action_writes_log_message(tmp_path: Path) -> None:
    logger = AppLogger()
    messages: list[str] = []
    logger.subscribe(messages.append)
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), logger)

    controller.placeholder_action("Проверить браузер")

    assert messages[-1].endswith("Проверить браузер пока не реализовано.")


def test_discover_browser_updates_state(tmp_path: Path) -> None:
    class FakeWindow:
        title = "Chrome - Bybit"

        def child_titles(self):
            return ["Bybit P2P", "Orders"]

    class FakeFinder:
        def find_windows(self, browser_name: str):
            return [FakeWindow()]

    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        browser_discovery_service=BrowserDiscoveryService(finder=FakeFinder()),
    )

    state = controller.discover_browser("Chrome")

    assert state.browser.connection_status == "Подключено"
    assert state.browser.window_title == "Chrome - Bybit"
    assert state.browser.tabs_summary == "Bybit P2P\nOrders"


def test_run_merchant_cycle_uses_service(tmp_path: Path) -> None:
    class FakeGateway:
        def read_current_advertisement(self):
            return AdvertisementSnapshot("123", "81,12", "Покупка")

        def delete_advertisement(self, advertisement_id: str) -> None:
            return None

        def create_advertisement(self, settings):
            return AdvertisementSnapshot("456", settings.fixed_price, settings.trade_side)

        def search_merchant(self, account_name: str, depth: int, max_pages: int = 2):
            return MerchantSearchResult(found=True, page=1, position=3)

    service = MerchantCycleService(gateway=FakeGateway(), logger=AppLogger())
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        merchant_cycle_service=service,
    )

    result = controller.run_merchant_cycle(controller.default_state())

    assert result is not None
    assert result.success is True
    assert result.position == 3


def test_fill_advertisement_form_uses_existing_browser_service(tmp_path: Path) -> None:
    class FakeExistingBrowserService:
        def __init__(self) -> None:
            self.called = False

        def fill_advertisement_form(self, state) -> bool:
            self.called = True
            return True

    service = FakeExistingBrowserService()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_existing_browser_service=service,
    )

    result = controller.fill_advertisement_form(controller.default_state())

    assert result is True
    assert service.called is True


def test_fetch_current_price_updates_state(tmp_path: Path) -> None:
    class FakeExistingBrowserService:
        def fetch_current_price(self, window_title: str) -> str:
            assert window_title == "Chrome - Bybit"
            return "80,99"

    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_existing_browser_service=FakeExistingBrowserService(),
    )
    state = controller.default_state()
    state.browser.window_title = "Chrome - Bybit"
    state.advertisement.fixed_price = "80"

    updated_state = controller.fetch_current_price(state)

    assert updated_state.advertisement.fixed_price == "80,99"


def test_start_and_stop_merchant_search_use_service(tmp_path: Path) -> None:
    class FakeMerchantCycleService:
        def __init__(self) -> None:
            self.started_with = None
            self.stop_called = False

        def run_live_cycle(self, state, *, stop_requested, on_progress):
            self.started_with = state
            on_progress(1, 3, "Ищу")
            return "done"

        def request_stop(self) -> None:
            self.stop_called = True

    service = FakeMerchantCycleService()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        merchant_cycle_service=service,
    )
    state = controller.default_state()
    state.browser.window_title = "Chrome - Bybit"
    progress: list[tuple[int, int, str]] = []

    result = controller.start_merchant_search(
        state,
        on_progress=lambda page, position, status: progress.append((page, position, status)),
    )
    controller.stop_merchant_search()

    assert result == "done"
    assert service.started_with is state
    assert progress == [(1, 3, "Ищу")]
    assert service.stop_called is True


def test_run_listing_cycle_iteration_creates_collects_and_records_found_account(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    class FakeExistingBrowserService:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def create_advertisement(self, state):
            self.calls.append(("create_advertisement", state.browser.window_title))
            return AdvertisementSnapshot("ad-55", "80,51", "Покупка")

        def collect_all_merchants(self, window_title: str, depth: int):
            self.calls.append(("collect_all_merchants", window_title, depth))
            return ["Alpha", "Mannequin", "Omega"]

        def read_current_advertisement(self, window_title: str):
            self.calls.append(("read_current_advertisement", window_title))
            return AdvertisementSnapshot("ad-55", "80,51", "Покупка")

    service = FakeExistingBrowserService()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_existing_browser_service=service,
    )
    state = controller.default_state()
    state.browser.window_title = "Bybit"
    state.search.account_name = "Mannequin"
    state.search.depth = "4"

    found = controller.run_listing_cycle_iteration(state)

    assert found is True
    assert service.calls == [
        ("create_advertisement", "Bybit"),
        ("collect_all_merchants", "Bybit", 4),
        ("read_current_advertisement", "Bybit"),
    ]
    assert (tmp_path / "data" / "merchants_temp.txt").read_text(encoding="utf-8").splitlines() == [
        "Alpha",
        "Mannequin",
        "Omega",
    ]
    found_text = (tmp_path / "data" / "found_accounts.txt").read_text(encoding="utf-8")
    assert "Mannequin" in found_text
    assert "ad-55" in found_text


def test_run_listing_cycle_iteration_returns_false_when_account_not_found(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    class FakeExistingBrowserService:
        def __init__(self) -> None:
            self.read_current_advertisement_called = False

        def create_advertisement(self, state):
            return AdvertisementSnapshot("ad-1", "80,51", "Покупка")

        def collect_all_merchants(self, window_title: str, depth: int):
            return ["Alpha", "Omega"]

        def read_current_advertisement(self, window_title: str):
            self.read_current_advertisement_called = True
            return AdvertisementSnapshot("ad-1", "80,51", "Покупка")

    service = FakeExistingBrowserService()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_existing_browser_service=service,
    )
    state = controller.default_state()
    state.browser.window_title = "Bybit"
    state.search.account_name = "Mannequin"
    state.search.depth = "4"

    found = controller.run_listing_cycle_iteration(state)

    assert found is False
    assert service.read_current_advertisement_called is False
