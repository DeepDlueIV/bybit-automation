from __future__ import annotations

from pathlib import Path

from bybit_automation.models.app_state import AppState, SearchSettings
from bybit_automation.models.app_state import AdvertisementSettings, SearchSettings
from bybit_automation.models.merchant_cycle import AdvertisementSnapshot, MerchantCycleResult, MerchantSearchResult
from bybit_automation.services.logging_service import AppLogger
from bybit_automation.services.merchant_cycle_service import MerchantCycleService


def test_cycle_recreates_advertisement_until_merchant_found() -> None:
    class FakeGateway:
        def __init__(self) -> None:
            self.deleted_ids: list[str] = []
            self.create_calls = 0
            self.search_calls = 0

        def read_current_advertisement(self):
            return AdvertisementSnapshot("old-1", "77,50", "Покупка")

        def delete_advertisement(self, advertisement_id: str) -> None:
            self.deleted_ids.append(advertisement_id)

        def create_advertisement(self, settings: AdvertisementSettings):
            self.create_calls += 1
            return AdvertisementSnapshot(f"new-{self.create_calls}", settings.fixed_price, settings.trade_side)

        def search_merchant(self, account_name: str, depth: int, max_pages: int = 2):
            self.search_calls += 1
            if self.search_calls < 2:
                return MerchantSearchResult(found=False)
            return MerchantSearchResult(found=True, page=2, position=4)

    gateway = FakeGateway()
    service = MerchantCycleService(gateway=gateway, logger=AppLogger())

    result = service.run_cycle(
        AdvertisementSettings(fixed_price="81,12"),
        SearchSettings(account_name="Mannequin", depth="4"),
        max_attempts=2,
    )

    assert result.success is True
    assert result.advertisement_id == "new-1"
    assert result.page == 2
    assert gateway.deleted_ids == ["old-1"]


def test_cycle_returns_failure_after_all_attempts() -> None:
    class FakeGateway:
        def read_current_advertisement(self):
            return None

        def delete_advertisement(self, advertisement_id: str) -> None:
            return None

        def create_advertisement(self, settings: AdvertisementSettings):
            return AdvertisementSnapshot("new-1", settings.fixed_price, settings.trade_side)

        def search_merchant(self, account_name: str, depth: int, max_pages: int = 2):
            return MerchantSearchResult(found=False)

    service = MerchantCycleService(gateway=FakeGateway(), logger=AppLogger())

    result = service.run_cycle(
        AdvertisementSettings(),
        SearchSettings(account_name="MissingMerchant", depth="4"),
        max_attempts=2,
    )

    assert result.success is False
    assert result.attempts == 2


def test_live_cycle_recreates_ad_with_fresh_price_and_appends_found_record(tmp_path: Path) -> None:
    class FakeGateway:
        def __init__(self) -> None:
            self.deleted: list[str] = []
            self.created_prices: list[str] = []
            self.search_calls = 0

        def read_current_advertisement(self, window_title: str):
            if not self.created_prices:
                return AdvertisementSnapshot("old-1", "77,50", "Покупка")
            return AdvertisementSnapshot("new-1", self.created_prices[-1], "Покупка")

        def delete_current_advertisement(self, window_title: str) -> None:
            self.deleted.append(window_title)

        def fetch_current_price(self, window_title: str) -> str:
            return "81,31"

        def create_advertisement(self, state: AppState):
            self.created_prices.append(state.advertisement.fixed_price)
            return AdvertisementSnapshot("new-1", state.advertisement.fixed_price, state.advertisement.trade_side)

        def search_merchant(self, window_title: str, account_name: str, depth: int, stop_requested, on_progress):
            self.search_calls += 1
            if self.search_calls == 1:
                on_progress(4, 0, "Не найден")
                return MerchantSearchResult(found=False)
            on_progress(2, 5, "Найден")
            return MerchantSearchResult(found=True, page=2, position=5)

    logger = AppLogger()
    messages: list[str] = []
    logger.subscribe(messages.append)
    found_file = tmp_path / "found_accounts.txt"
    service = MerchantCycleService(gateway=FakeGateway(), logger=logger, found_accounts_file=found_file)

    state = AppState()
    state.browser.window_title = "Bybit - ILYA BB - 1"
    state.search = SearchSettings(account_name="Mannequin", depth="4")
    state.advertisement.fixed_price = "80,00"

    progress_updates: list[tuple[int, int, str]] = []
    result = service.run_live_cycle(
        state,
        stop_requested=lambda: False,
        on_progress=lambda page, position, status: progress_updates.append((page, position, status)),
    )

    assert result.success is True
    assert result.stopped is False
    assert result.advertisement_id == "new-1"
    assert result.price == "81,31"
    assert progress_updates == [(4, 0, "Не найден"), (2, 5, "Найден")]
    assert "страница 2" in found_file.read_text(encoding="utf-8")
    assert "строка 5/10" in found_file.read_text(encoding="utf-8")
    assert "id new-1" in found_file.read_text(encoding="utf-8")
    assert "цена 81,31" in found_file.read_text(encoding="utf-8")


def test_live_cycle_stops_without_recreating_after_stop_request(tmp_path: Path) -> None:
    class FakeGateway:
        def __init__(self) -> None:
            self.deleted = 0
            self.created = 0

        def read_current_advertisement(self, window_title: str):
            return AdvertisementSnapshot("old-1", "77,50", "Покупка")

        def delete_current_advertisement(self, window_title: str) -> None:
            self.deleted += 1

        def fetch_current_price(self, window_title: str) -> str:
            return "81,31"

        def create_advertisement(self, state: AppState):
            self.created += 1
            return AdvertisementSnapshot("new-1", state.advertisement.fixed_price, state.advertisement.trade_side)

        def search_merchant(self, window_title: str, account_name: str, depth: int, stop_requested, on_progress):
            on_progress(4, 0, "Не найден")
            return MerchantSearchResult(found=False)

    gateway = FakeGateway()
    service = MerchantCycleService(gateway=gateway, logger=AppLogger(), found_accounts_file=tmp_path / "found_accounts.txt")
    state = AppState()
    state.browser.window_title = "Bybit - ILYA BB - 1"
    state.search = SearchSettings(account_name="Mannequin", depth="4")

    result = service.run_live_cycle(
        state,
        stop_requested=lambda: True,
        on_progress=lambda *_: None,
    )

    assert result == MerchantCycleResult(success=False, stopped=True, attempts=0, message="Поиск остановлен.")
    assert gateway.deleted == 0
    assert gateway.created == 0


def test_live_cycle_continues_when_delete_button_is_missing(tmp_path: Path) -> None:
    class FakeGateway:
        def __init__(self) -> None:
            self.created_prices: list[str] = []
            self.search_calls = 0

        def read_current_advertisement(self, window_title: str):
            if not self.created_prices:
                return AdvertisementSnapshot("old-1", "77,50", "Покупка")
            return AdvertisementSnapshot("new-1", self.created_prices[-1], "Покупка")

        def delete_current_advertisement(self, window_title: str) -> None:
            raise RuntimeError("Не удалось найти кнопку удаления объявления.")

        def fetch_current_price(self, window_title: str) -> str:
            return "81,31"

        def create_advertisement(self, state: AppState):
            self.created_prices.append(state.advertisement.fixed_price)
            return AdvertisementSnapshot("new-1", state.advertisement.fixed_price, state.advertisement.trade_side)

        def search_merchant(self, window_title: str, account_name: str, depth: int, stop_requested, on_progress):
            self.search_calls += 1
            if self.search_calls == 1:
                return MerchantSearchResult(found=False)
            return MerchantSearchResult(found=True, page=1, position=1)

    service = MerchantCycleService(gateway=FakeGateway(), logger=AppLogger(), found_accounts_file=tmp_path / "found_accounts.txt")
    state = AppState()
    state.browser.window_title = "Bybit - ILYA BB - 1"
    state.search = SearchSettings(account_name="Mannequin", depth="1")

    result = service.run_live_cycle(
        state,
        stop_requested=lambda: False,
        on_progress=lambda *_: None,
    )

    assert result.success is True
    assert result.advertisement_id == "new-1"
    assert result.price == "81,31"
