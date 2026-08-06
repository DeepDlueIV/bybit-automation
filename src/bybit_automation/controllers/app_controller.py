from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Protocol

from bybit_automation.infrastructure.paths import AppPaths
from bybit_automation.models.automation_mode import AutomationMode
from bybit_automation.models.app_state import AppState
from bybit_automation.models.browser_discovery import BrowserDiscoveryResult
from bybit_automation.models.merchant_cycle import MerchantCycleResult
from bybit_automation.models.order_detection import OrderDetectionResult
from bybit_automation.services.browser_discovery_service import BrowserDiscoveryService
from bybit_automation.services.bybit_existing_browser_service import BybitExistingBrowserService
from bybit_automation.services.logging_service import AppLogger
from bybit_automation.services.merchant_cycle_service import MerchantCycleService
from bybit_automation.services.settings_service import JsonSettingsService


class PositionSoundNotifier(Protocol):
    def notify(self) -> None:
        ...


def position_range_label(position: int) -> str:
    if position < 1:
        return ""
    return str(position)


class AppController:
    def __init__(
        self,
        settings_service: JsonSettingsService,
        logger: AppLogger,
        browser_discovery_service: BrowserDiscoveryService | None = None,
        merchant_cycle_service: MerchantCycleService | None = None,
        bybit_existing_browser_service: BybitExistingBrowserService | None = None,
        bybit_browser_services: dict[str, Any] | None = None,
        merchant_cycle_services: dict[str, MerchantCycleService] | None = None,
        position_sound_notifier: PositionSoundNotifier | None = None,
        app_paths: AppPaths | None = None,
        default_state: AppState | None = None,
    ) -> None:
        self._settings_service = settings_service
        self._logger = logger
        self._browser_discovery_service = browser_discovery_service
        self._merchant_cycle_service = merchant_cycle_service
        self._bybit_existing_browser_service = bybit_existing_browser_service
        self._bybit_browser_services = bybit_browser_services or {}
        if bybit_existing_browser_service is not None:
            self._bybit_browser_services.setdefault(AutomationMode.INCOGNITON_UIA, bybit_existing_browser_service)
        self._merchant_cycle_services = merchant_cycle_services or {}
        if merchant_cycle_service is not None:
            self._merchant_cycle_services.setdefault(AutomationMode.INCOGNITON_UIA, merchant_cycle_service)
        self._position_sound_notifier = position_sound_notifier
        self._app_paths = app_paths or AppPaths.from_cwd()
        self._default_state = AppState.from_dict((default_state or AppState()).to_dict())
        self._last_found_position = 0
        self._last_found_position_range = ""

    @property
    def last_found_position(self) -> int:
        return self._last_found_position

    @property
    def last_found_position_range(self) -> str:
        return self._last_found_position_range

    def default_state(self) -> AppState:
        return AppState.from_dict(self._default_state.to_dict())

    def save_settings(self, state: AppState) -> None:
        self._settings_service.save(state)
        self._logger.info("Настройки сохранены.")

    def load_settings(self) -> AppState:
        state = self._settings_service.load()
        self._logger.info("Настройки загружены.")
        return state

    def reset_settings(self) -> AppState:
        self._logger.info("Настройки сброшены к значениям по умолчанию.")
        return self.default_state()

    def placeholder_action(self, action_name: str) -> None:
        self._logger.info(f"{action_name} пока не реализовано.")

    def open_selected_browser_profile(self, state: AppState) -> bool:
        profile_modes = {
            AutomationMode.PLAYWRIGHT_PROFILE,
            AutomationMode.PLAYWRIGHT_CHROMIUM_EXTENSIONS,
            AutomationMode.SYSTEM_CHROME_EXTENSIONS_PROFILE,
            AutomationMode.SYSTEM_CHROME_EXTENSIONS_RECOVERY,
            AutomationMode.PORTABLE_CHROME,
        }
        if state.browser.automation_mode not in profile_modes:
            self._logger.info("Profile opener is available only for Playwright/System Chrome profile modes.")
            return False
            self._logger.info("Открытие Playwright-профиля доступно только в режиме Playwright profile.")
            return False
        browser_service = self._browser_service_for(state)
        if browser_service is None or not hasattr(browser_service, "open_profile"):
            self._logger.info("Выбранный режим не поддерживает отдельное открытие профиля.")
            return False
        self._logger.info(
            f"Opening browser profile: browser={state.browser.browser_name}; automation={state.browser.automation_mode}."
        )
        browser_service.open_profile(state.browser.window_title)
        return True

    def _browser_service_for(self, state: AppState) -> Any | None:
        return self._bybit_browser_services.get(state.browser.automation_mode) or self._bybit_existing_browser_service

    def _merchant_cycle_service_for(self, state: AppState) -> MerchantCycleService | None:
        return self._merchant_cycle_services.get(state.browser.automation_mode) or self._merchant_cycle_service

    def discover_browser(self, browser_name: str) -> AppState:
        if self._browser_discovery_service is None:
            self._logger.info("Сервис поиска браузера не подключен.")
            return AppState()

        result = self._browser_discovery_service.discover(browser_name)
        return self._state_from_browser_discovery(result)

    def discover_browser_for_state(self, state: AppState) -> AppState:
        if state.browser.automation_mode in {
            AutomationMode.SYSTEM_CHROME_EXTENSIONS_PROFILE,
            AutomationMode.SYSTEM_CHROME_EXTENSIONS_RECOVERY,
            AutomationMode.PORTABLE_CHROME,
        }:
            browser_service = self._browser_service_for(state)
            if browser_service is not None and hasattr(browser_service, "discover_profile"):
                return self._state_from_browser_discovery(browser_service.discover_profile())
        return self.discover_browser(state.browser.browser_name)

    def _state_from_browser_discovery(self, result: BrowserDiscoveryResult) -> AppState:
        state = AppState.from_browser_discovery(result)
        summary = ", ".join(tab.title for tab in result.tabs) if result.tabs else "вкладки не найдены"
        self._logger.info(f"Браузер: {result.window_title or 'не найден'}; вкладки: {summary}")
        return state

    def run_merchant_cycle(self, state: AppState, *, max_attempts: int = 3) -> MerchantCycleResult | None:
        merchant_cycle_service = self._merchant_cycle_service_for(state)
        if merchant_cycle_service is None:
            self._logger.info("Сервис цикла Bybit пока не подключен.")
            return None
        return merchant_cycle_service.run_cycle(
            state.advertisement,
            state.search,
            max_attempts=max_attempts,
        )

    def start_merchant_search(self, state: AppState, *, on_progress) -> MerchantCycleResult | None:
        merchant_cycle_service = self._merchant_cycle_service_for(state)
        if merchant_cycle_service is None:
            self._logger.info("Сервис live-поиска Bybit пока не подключен.")
            return None
        return merchant_cycle_service.run_live_cycle(
            state,
            stop_requested=lambda: False,
            on_progress=on_progress,
        )

    def stop_merchant_search(self) -> None:
        services = list(self._merchant_cycle_services.values())
        if self._merchant_cycle_service is not None:
            services.append(self._merchant_cycle_service)
        seen: set[int] = set()
        for service in services:
            if id(service) in seen:
                continue
            seen.add(id(service))
            if service is not None:
                service.request_stop()

    def fill_advertisement_form(self, state: AppState) -> bool:
        browser_service = self._browser_service_for(state)
        if browser_service is None:
            self._logger.info("Сервис заполнения формы в текущем браузере пока не подключен.")
            return False
        return browser_service.fill_advertisement_form(state)

    def collect_all_merchants(self, state: AppState) -> list[str]:
        browser_service = self._browser_service_for(state)
        if browser_service is None:
            self._logger.info("Сервис сбора мерчантов пока не подключен.")
            return []
        depth = int(state.search.depth) if state.search.depth and state.search.depth.isdigit() else 4
        return browser_service.collect_all_merchants(
            state.browser.window_title, depth
        )

    def run_listing_cycle_iteration(self, state: AppState, *, stop_check: Callable[[], bool] = lambda: False) -> bool:
        browser_service = self._browser_service_for(state)
        if browser_service is None:
            self._logger.info("Сервис Bybit для цикла пока не подключён.")
            return False

        if stop_check():
            return False

        account_name = state.search.account_name.strip()
        if not account_name:
            raise RuntimeError("Укажи имя аккаунта для цикла.")
        if not state.browser.window_title.strip():
            raise RuntimeError("Сначала нужно определить рабочее окно браузера.")

        if stop_check():
            return False

        depth = int(state.search.depth) if state.search.depth and state.search.depth.isdigit() else 4
        self._logger.info("Цикл: удаляю старое объявление и создаю новое.")
        browser_service.create_advertisement(state)

        if stop_check():
            return False

        self._logger.info(f"Цикл: собираю мерчантов, глубина {depth} страниц.")
        merchants = browser_service.collect_all_merchants(state.browser.window_title, depth)
        temp_path = self._app_paths.data_dir / "merchants_temp.txt"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text("\n".join(merchants) + ("\n" if merchants else ""), encoding="utf-8")
        self._logger.info(f"Цикл: собрано мерчантов: {len(merchants)}. Сохранено: {temp_path}")

        if stop_check():
            return False

        found_position = self._find_merchant_position(merchants, account_name)
        if found_position == 0:
            self._logger.info(f"Цикл: аккаунт '{account_name}' не найден. Начинаю новую итерацию.")
            return False

        try:
            snapshot = browser_service.read_current_advertisement(state.browser.window_title)
        except Exception as error:
            self._logger.info(f"Цикл: не удалось прочитать объявление: {error}")
            snapshot = None
        self._append_found_account_from_cycle(account_name, found_position, snapshot)
        self._record_found_position(found_position)
        self._notify_found_account_recorded()
        self._logger.info(f"Цикл: аккаунт '{account_name}' найден на позиции {found_position}. Результат записан.")
        return True

    def detect_orders(self, state: AppState) -> OrderDetectionResult:
        """Проверяет страницу заказов только в Playwright/CDP-режиме."""
        service = self._browser_service_for(state)
        if service is None or not hasattr(service, "detect_orders"):
            raise RuntimeError("Обнаружение ордеров доступно только в Playwright/CDP-режимах.")
        return service.detect_orders(state.browser.window_title)

    def _find_merchant_position(self, merchants: list[str], account_name: str) -> int:
        target = self._normalize_merchant_name(account_name)
        for index, merchant in enumerate(merchants, start=1):
            if self._normalize_merchant_name(merchant) == target:
                return index
        return 0

    def _normalize_merchant_name(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s.-]+", " ", text, flags=re.UNICODE)).strip().lower()

    def _append_found_account_from_cycle(self, account_name: str, position: int, snapshot) -> None:
        found_file = self._app_paths.found_accounts_file
        found_file.parent.mkdir(parents=True, exist_ok=True)
        self._logger.info(f"Записываю аккаунт '{account_name}' позиция {position} в {found_file}")
        with found_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{account_name}\n")
            handle.write(f"Позиция {position}\n")
            if snapshot is not None:
                handle.write(f"ID {snapshot.advertisement_id}\n")
                handle.write(f"Цена {snapshot.price}\n")
                if snapshot.created_at:
                    handle.write(f"Дата объявления {snapshot.created_at}\n")
            handle.write("\n")
        self._logger.info(f"Запись '{account_name}' завершена.")

    def _record_found_position(self, position: int) -> None:
        self._last_found_position = position
        self._last_found_position_range = position_range_label(position)

    def _notify_found_account_recorded(self) -> None:
        if self._position_sound_notifier is None:
            return
        self._position_sound_notifier.notify()
        self._logger.info("Звуковое уведомление о найденном аккаунте отправлено.")

    def find_my_account(self, state: AppState) -> None:
        browser_service = self._browser_service_for(state)
        if browser_service is None:
            self._logger.info("Сервис поиска Bybit пока не подключен.")
            return

        account_name = state.search.account_name.strip()
        if not account_name:
            self._logger.info("Не указано имя аккаунта для поиска.")
            return

        temp_path = self._app_paths.data_dir / "merchants_temp.txt"
        if not temp_path.exists():
            self._logger.info("Файл merchants_temp.txt не найден. Сначала соберите мерчантов.")
            return

        lines = temp_path.read_text(encoding="utf-8").strip().splitlines()
        found_idx = -1
        for i, line in enumerate(lines, start=1):
            if line.strip().lower() == account_name.lower():
                found_idx = i
                break

        if found_idx == -1:
            self._logger.info(f"Аккаунт '{account_name}' не найден в списке мерчантов.")
            return

        self._logger.info(f"Аккаунт '{account_name}' найден на позиции {found_idx}. Читаю данные объявления.")

        try:
            snapshot = browser_service.read_current_advertisement(state.browser.window_title)
        except Exception as error:
            self._logger.info(f"Не удалось прочитать объявление: {error}")
            snapshot = None

        found_file = self._app_paths.found_accounts_file
        with open(found_file, "a", encoding="utf-8") as f:
            f.write(f"{account_name}\n")
            f.write(f"Позиция {found_idx}\n")
            if snapshot:
                f.write(f"ID {snapshot.advertisement_id}\n")
                f.write(f"Цена {snapshot.price}\n")
                if snapshot.created_at:
                    f.write(f"Дата объявления {snapshot.created_at}\n")
            f.write("\n")

        self._record_found_position(found_idx)
        self._notify_found_account_recorded()
        self._logger.info(f"Аккаунт '{account_name}' найден на позиции {found_idx}. Данные добавлены в found_accounts.txt.")

    def fetch_current_price(self, state: AppState) -> AppState:
        browser_service = self._browser_service_for(state)
        if browser_service is None:
            self._logger.info("Сервис чтения цены из текущего браузера пока не подключен.")
            return state
        price = browser_service.fetch_current_price(state.browser.window_title)
        updated_state = AppState.from_dict(state.to_dict())
        updated_state.advertisement.fixed_price = price
        self._logger.info(f"Подтянул актуальную цену: {price}")
        return updated_state

    def diagnose_sell_page(self, state: AppState) -> Path | None:
        browser_service = self._browser_service_for(state)
        if browser_service is None or not hasattr(browser_service, "diagnose_sell_page"):
            self._logger.info("Sell-диагностика недоступна для выбранного режима браузера.")
            return None
        return browser_service.diagnose_sell_page(state.browser.window_title)

    def diagnose_ads_page(self, state: AppState) -> Path | None:
        browser_service = self._browser_service_for(state)
        if browser_service is None or not hasattr(browser_service, "diagnose_ads_page"):
            self._logger.info("Ads-диагностика недоступна для выбранного режима браузера.")
            return None
        return browser_service.diagnose_ads_page(state.browser.window_title)

    def open_ads_form_for_smoke_check(self, state: AppState) -> bool:
        browser_service = self._browser_service_for(state)
        if browser_service is None or not hasattr(browser_service, "open_ads_form_for_smoke_check"):
            self._logger.info("Открытие формы Ads недоступно для выбранного режима браузера.")
            return False
        browser_service.open_ads_form_for_smoke_check(state.browser.window_title)
        return True
