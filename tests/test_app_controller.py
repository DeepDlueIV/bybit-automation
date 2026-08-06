from __future__ import annotations

from pathlib import Path

from bybit_automation.controllers.app_controller import AppController, position_range_label
from bybit_automation.infrastructure.paths import AppPaths
from bybit_automation.models.automation_mode import AutomationMode
from bybit_automation.models.merchant_cycle import AdvertisementSnapshot, MerchantSearchResult
from bybit_automation.models.browser_discovery import BrowserDiscoveryResult, BrowserTabInfo
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

    state = controller.discover_browser("System Chrome")

    assert state.browser.connection_status == "Подключено"
    assert state.browser.window_title == "Chrome - Bybit"
    assert state.browser.tabs_summary == "Bybit P2P\nOrders"


def test_system_chrome_extensions_profile_uses_cdp_profile_discovery(tmp_path: Path) -> None:
    class CdpProfileService:
        def discover_profile(self) -> BrowserDiscoveryResult:
            return BrowserDiscoveryResult(
                browser_name="System Chrome",
                window_title="System Chrome extensions profile",
                tabs=[BrowserTabInfo(title="Bybit P2P", role="other")],
                ads_tab_title="",
                sell_tab_title="",
                connected=True,
            )

    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_browser_services={AutomationMode.SYSTEM_CHROME_EXTENSIONS_PROFILE: CdpProfileService()},
    )
    state = controller.default_state()
    state.browser.browser_name = "Playwright Chromium"
    state.browser.automation_mode = AutomationMode.SYSTEM_CHROME_EXTENSIONS_PROFILE

    discovered = controller.discover_browser_for_state(state)

    assert discovered.browser.connection_status == "Подключено"
    assert discovered.browser.window_title == "System Chrome extensions profile"
    assert discovered.browser.tabs_summary == "Bybit P2P"


def test_recovery_mode_can_open_profile(tmp_path: Path) -> None:
    class FakeService:
        def __init__(self) -> None:
            self.opened = False

        def open_profile(self, window_title: str) -> None:
            self.opened = True

    service = FakeService()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_browser_services={AutomationMode.SYSTEM_CHROME_EXTENSIONS_RECOVERY: service},
    )
    state = controller.default_state()
    state.browser.automation_mode = AutomationMode.SYSTEM_CHROME_EXTENSIONS_RECOVERY

    assert controller.open_selected_browser_profile(state) is True
    assert service.opened is True


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
    test_paths = AppPaths(root_dir=tmp_path, data_dir=tmp_path / "data", settings_file=tmp_path / "settings.json", found_accounts_file=tmp_path / "data" / "found_accounts.txt", log_file=tmp_path / "data" / "app.log")

    class FakeNotifier:
        def __init__(self) -> None:
            self.calls = 0

        def notify(self) -> None:
            self.calls += 1

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
            return AdvertisementSnapshot("ad-55", "80,51", "Покупка", "2026-07-04 22:19:47")

    service = FakeExistingBrowserService()
    notifier = FakeNotifier()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_existing_browser_service=service,
        position_sound_notifier=notifier,
        app_paths=test_paths,
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
    assert "Цена 80,51" in found_text
    assert "Дата объявления 2026-07-04 22:19:47" in found_text
    assert controller.last_found_position_range == "2"
    assert notifier.calls == 1


def test_run_listing_cycle_iteration_uses_selected_automation_mode_service(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    test_paths = AppPaths(root_dir=tmp_path, data_dir=tmp_path / "data", settings_file=tmp_path / "settings.json", found_accounts_file=tmp_path / "data" / "found_accounts.txt", log_file=tmp_path / "data" / "app.log")

    class FailingUiaService:
        def create_advertisement(self, state):
            raise AssertionError("UIA service must not be used for Playwright profile mode")

    class FakePlaywrightService:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def create_advertisement(self, state):
            self.calls.append(("create_advertisement", state.browser.automation_mode))
            return AdvertisementSnapshot("pw-ad-1", "82,01", "Покупка")

        def collect_all_merchants(self, window_title: str, depth: int):
            self.calls.append(("collect_all_merchants", window_title, depth))
            return ["Alpha", "Mannequin"]

        def read_current_advertisement(self, window_title: str):
            self.calls.append(("read_current_advertisement", window_title))
            return AdvertisementSnapshot("pw-ad-1", "82,01", "Покупка", "2026-07-06 12:00:00")

    playwright_service = FakePlaywrightService()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_existing_browser_service=FailingUiaService(),
        bybit_browser_services={AutomationMode.PLAYWRIGHT_PROFILE: playwright_service},
        app_paths=test_paths,
    )
    state = controller.default_state()
    state.browser.automation_mode = AutomationMode.PLAYWRIGHT_PROFILE
    state.browser.window_title = "Playwright profile"
    state.search.account_name = "Mannequin"
    state.search.depth = "2"

    found = controller.run_listing_cycle_iteration(state)

    assert found is True
    assert playwright_service.calls == [
        ("create_advertisement", AutomationMode.PLAYWRIGHT_PROFILE),
        ("collect_all_merchants", "Playwright profile", 2),
        ("read_current_advertisement", "Playwright profile"),
    ]


def test_open_selected_browser_profile_uses_selected_automation_mode_service(tmp_path: Path) -> None:
    class FakePlaywrightService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def open_profile(self, window_title: str) -> None:
            self.calls.append(("open_profile", window_title))

    playwright_service = FakePlaywrightService()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_browser_services={AutomationMode.PLAYWRIGHT_PROFILE: playwright_service},
    )
    state = controller.default_state()
    state.browser.automation_mode = AutomationMode.PLAYWRIGHT_PROFILE
    state.browser.window_title = "Playwright profile"

    result = controller.open_selected_browser_profile(state)

    assert result is True
    assert playwright_service.calls == [("open_profile", "Playwright profile")]


def test_open_selected_browser_profile_allows_new_extension_profile_modes(tmp_path: Path) -> None:
    class FakeProfileService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def open_profile(self, window_title: str) -> None:
            self.calls.append(window_title)

    chromium_service = FakeProfileService()
    chrome_service = FakeProfileService()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_browser_services={
            AutomationMode.PLAYWRIGHT_CHROMIUM_EXTENSIONS: chromium_service,
            AutomationMode.SYSTEM_CHROME_EXTENSIONS_PROFILE: chrome_service,
        },
    )

    state = controller.default_state()
    state.browser.automation_mode = AutomationMode.PLAYWRIGHT_CHROMIUM_EXTENSIONS
    state.browser.window_title = "chromium"
    assert controller.open_selected_browser_profile(state) is True

    state.browser.automation_mode = AutomationMode.SYSTEM_CHROME_EXTENSIONS_PROFILE
    state.browser.window_title = "chrome"
    assert controller.open_selected_browser_profile(state) is True

    assert chromium_service.calls == ["chromium"]
    assert chrome_service.calls == ["chrome"]


def test_open_selected_browser_profile_does_not_call_uia_fallback(tmp_path: Path) -> None:
    class ExistingBrowserServiceThatWouldCrash:
        def open_profile(self, window_title: str) -> None:
            raise AssertionError("UIA service must not be used for Playwright profile opener")

    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_existing_browser_service=ExistingBrowserServiceThatWouldCrash(),
    )
    state = controller.default_state()
    state.browser.automation_mode = AutomationMode.INCOGNITON_UIA

    result = controller.open_selected_browser_profile(state)

    assert result is False


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


def test_position_range_label_groups_absolute_positions() -> None:
    assert position_range_label(1) == "1"
    assert position_range_label(10) == "10"
    assert position_range_label(11) == "11"
    assert position_range_label(20) == "20"
    assert position_range_label(0) == ""


def test_find_my_account_records_advertisement_created_at_and_notifies_after_successful_write(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    test_paths = AppPaths(root_dir=tmp_path, data_dir=tmp_path / "data", settings_file=tmp_path / "settings.json", found_accounts_file=tmp_path / "data" / "found_accounts.txt", log_file=tmp_path / "data" / "app.log")

    class FakeNotifier:
        def __init__(self) -> None:
            self.calls = 0

        def notify(self) -> None:
            self.calls += 1

    class FakeExistingBrowserService:
        def read_current_advertisement(self, window_title: str):
            return AdvertisementSnapshot("ad-77", "81,02", "Покупка", "2026-07-04 22:19:47")

    temp_path = tmp_path / "data" / "merchants_temp.txt"
    temp_path.parent.mkdir(parents=True)
    temp_path.write_text("Alpha\nMannequin\nOmega\n", encoding="utf-8")
    notifier = FakeNotifier()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_existing_browser_service=FakeExistingBrowserService(),
        position_sound_notifier=notifier,
        app_paths=test_paths,
    )
    state = controller.default_state()
    state.browser.window_title = "Bybit"
    state.search.account_name = "Mannequin"

    controller.find_my_account(state)

    found_text = (tmp_path / "data" / "found_accounts.txt").read_text(encoding="utf-8")
    assert "ID ad-77" in found_text
    assert "Цена 81,02" in found_text
    assert "Дата объявления 2026-07-04 22:19:47" in found_text
    assert controller.last_found_position_range == "2"
    assert notifier.calls == 1


def test_find_merchant_position_uses_same_normalization_as_browser_driver(tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())

    position = controller._find_merchant_position(["Alpha", "🎆 Mannequin 🀄", "Omega"], "Mannequin")

    assert position == 2


def test_find_my_account_notifies_for_position_outside_top_10_after_successful_write(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    test_paths = AppPaths(root_dir=tmp_path, data_dir=tmp_path / "data", settings_file=tmp_path / "settings.json", found_accounts_file=tmp_path / "data" / "found_accounts.txt", log_file=tmp_path / "data" / "app.log")

    class FakeNotifier:
        def __init__(self) -> None:
            self.calls = 0

        def notify(self) -> None:
            self.calls += 1

    class FakeExistingBrowserService:
        def read_current_advertisement(self, window_title: str):
            return AdvertisementSnapshot("ad-88", "81,02", "РџРѕРєСѓРїРєР°", "2026-07-04 22:19:47")

    temp_path = tmp_path / "data" / "merchants_temp.txt"
    temp_path.parent.mkdir(parents=True)
    temp_path.write_text("\n".join([f"Merchant{i}" for i in range(1, 12)]) + "\nMannequin\n", encoding="utf-8")
    notifier = FakeNotifier()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_existing_browser_service=FakeExistingBrowserService(),
        position_sound_notifier=notifier,
        app_paths=test_paths,
    )
    state = controller.default_state()
    state.browser.window_title = "Bybit"
    state.search.account_name = "Mannequin"

    controller.find_my_account(state)

    assert controller.last_found_position_range == "12"
    assert notifier.calls == 1


def test_find_my_account_does_not_notify_when_found_file_write_fails(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    test_paths = AppPaths(root_dir=tmp_path, data_dir=tmp_path / "data", settings_file=tmp_path / "settings.json", found_accounts_file=tmp_path / "data" / "found_accounts.txt", log_file=tmp_path / "data" / "app.log")

    class FakeNotifier:
        def __init__(self) -> None:
            self.calls = 0

        def notify(self) -> None:
            self.calls += 1

    class FakeExistingBrowserService:
        def read_current_advertisement(self, window_title: str):
            return AdvertisementSnapshot("ad-77", "81,02", "РџРѕРєСѓРїРєР°", "2026-07-04 22:19:47")

    temp_path = tmp_path / "data" / "merchants_temp.txt"
    temp_path.parent.mkdir(parents=True)
    temp_path.write_text("Alpha\nMannequin\nOmega\n", encoding="utf-8")
    notifier = FakeNotifier()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_existing_browser_service=FakeExistingBrowserService(),
        position_sound_notifier=notifier,
        app_paths=test_paths,
    )
    state = controller.default_state()
    state.browser.window_title = "Bybit"
    state.search.account_name = "Mannequin"

    def fail_open(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", fail_open)

    try:
        controller.find_my_account(state)
    except OSError:
        pass
    else:
        raise AssertionError("expected OSError")

    assert notifier.calls == 0


def test_run_listing_cycle_writes_account_when_read_snapshot_raises_oserror(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    test_paths = AppPaths(root_dir=tmp_path, data_dir=tmp_path / "data", settings_file=tmp_path / "settings.json", found_accounts_file=tmp_path / "data" / "found_accounts.txt", log_file=tmp_path / "data" / "app.log")

    class FakeExistingBrowserService:
        def create_advertisement(self, state):
            return AdvertisementSnapshot("ad-1", "80,00", "Покупка")

        def collect_all_merchants(self, window_title: str, depth: int):
            return ["Alpha", "Mannequin", "Omega"]

        def read_current_advertisement(self, window_title: str):
            raise OSError("UIA element is stale")

    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_existing_browser_service=FakeExistingBrowserService(),
        app_paths=test_paths,
    )
    state = controller.default_state()
    state.browser.window_title = "Bybit"
    state.search.account_name = "Mannequin"
    state.search.depth = "4"

    found = controller.run_listing_cycle_iteration(state)

    assert found is True
    found_text = (tmp_path / "data" / "found_accounts.txt").read_text(encoding="utf-8")
    assert "Mannequin" in found_text
    assert "Позиция 2" in found_text


def test_open_ads_form_for_smoke_check_uses_selected_browser_service(tmp_path: Path) -> None:
    class FakeService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def open_ads_form_for_smoke_check(self, window_title: str) -> None:
            self.calls.append(("open_ads_form_for_smoke_check", window_title))

    service = FakeService()
    controller = AppController(
        JsonSettingsService(tmp_path / "settings.json"),
        AppLogger(),
        bybit_browser_services={AutomationMode.PLAYWRIGHT_PROFILE: service},
    )
    state = controller.default_state()
    state.browser.automation_mode = AutomationMode.PLAYWRIGHT_PROFILE
    state.browser.window_title = "Bybit"

    result = controller.open_ads_form_for_smoke_check(state)

    assert result is True
    assert service.calls == [("open_ads_form_for_smoke_check", "Bybit")]
