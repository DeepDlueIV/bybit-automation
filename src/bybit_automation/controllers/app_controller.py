from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

from bybit_automation.infrastructure.paths import AppPaths
from bybit_automation.models.app_state import AppState
from bybit_automation.models.merchant_cycle import MerchantCycleResult
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
        position_sound_notifier: PositionSoundNotifier | None = None,
        app_paths: AppPaths | None = None,
    ) -> None:
        self._settings_service = settings_service
        self._logger = logger
        self._browser_discovery_service = browser_discovery_service
        self._merchant_cycle_service = merchant_cycle_service
        self._bybit_existing_browser_service = bybit_existing_browser_service
        self._position_sound_notifier = position_sound_notifier
        self._app_paths = app_paths or AppPaths.from_cwd()
        self._last_found_position = 0
        self._last_found_position_range = ""

    @property
    def last_found_position(self) -> int:
        return self._last_found_position

    @property
    def last_found_position_range(self) -> str:
        return self._last_found_position_range

    def default_state(self) -> AppState:
        return AppState()

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

    def discover_browser(self, browser_name: str) -> AppState:
        if self._browser_discovery_service is None:
            self._logger.info("Сервис поиска браузера не подключен.")
            return AppState()

        result = self._browser_discovery_service.discover(browser_name)
        state = AppState.from_browser_discovery(result)
        summary = ", ".join(tab.title for tab in result.tabs) if result.tabs else "вкладки не найдены"
        self._logger.info(f"Браузер: {result.window_title or 'не найден'}; вкладки: {summary}")
        return state

    def run_merchant_cycle(self, state: AppState, *, max_attempts: int = 3) -> MerchantCycleResult | None:
        if self._merchant_cycle_service is None:
            self._logger.info("Сервис цикла Bybit пока не подключен.")
            return None
        return self._merchant_cycle_service.run_cycle(
            state.advertisement,
            state.search,
            max_attempts=max_attempts,
        )

    def start_merchant_search(self, state: AppState, *, on_progress) -> MerchantCycleResult | None:
        if self._merchant_cycle_service is None:
            self._logger.info("Сервис live-поиска Bybit пока не подключен.")
            return None
        return self._merchant_cycle_service.run_live_cycle(
            state,
            stop_requested=lambda: False,
            on_progress=on_progress,
        )

    def stop_merchant_search(self) -> None:
        if self._merchant_cycle_service is None:
            return
        self._merchant_cycle_service.request_stop()

    def fill_advertisement_form(self, state: AppState) -> bool:
        if self._bybit_existing_browser_service is None:
            self._logger.info("Сервис заполнения формы в текущем браузере пока не подключен.")
            return False
        return self._bybit_existing_browser_service.fill_advertisement_form(state)

    def collect_all_merchants(self, state: AppState) -> list[str]:
        if self._bybit_existing_browser_service is None:
            self._logger.info("Сервис сбора мерчантов пока не подключен.")
            return []
        depth = int(state.search.depth) if state.search.depth and state.search.depth.isdigit() else 4
        return self._bybit_existing_browser_service.collect_all_merchants(
            state.browser.window_title, depth
        )

    def run_listing_cycle_iteration(self, state: AppState, *, stop_check: Callable[[], bool] = lambda: False) -> bool:
        if self._bybit_existing_browser_service is None:
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
        self._bybit_existing_browser_service.create_advertisement(state)

        if stop_check():
            return False

        self._logger.info(f"Цикл: собираю мерчантов, глубина {depth} страниц.")
        merchants = self._bybit_existing_browser_service.collect_all_merchants(state.browser.window_title, depth)
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
            snapshot = self._bybit_existing_browser_service.read_current_advertisement(state.browser.window_title)
        except Exception as error:
            self._logger.info(f"Цикл: не удалось прочитать объявление: {error}")
            snapshot = None
        self._append_found_account_from_cycle(account_name, found_position, snapshot)
        self._record_found_position(found_position)
        self._notify_found_account_recorded()
        self._logger.info(f"Цикл: аккаунт '{account_name}' найден на позиции {found_position}. Результат записан.")
        return True

    def _find_merchant_position(self, merchants: list[str], account_name: str) -> int:
        target = account_name.strip().lower()
        for index, merchant in enumerate(merchants, start=1):
            if merchant.strip().lower() == target:
                return index
        return 0

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
        if self._bybit_existing_browser_service is None:
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
            snapshot = self._bybit_existing_browser_service.read_current_advertisement(state.browser.window_title)
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
        if self._bybit_existing_browser_service is None:
            self._logger.info("Сервис чтения цены из текущего браузера пока не подключен.")
            return state
        price = self._bybit_existing_browser_service.fetch_current_price(state.browser.window_title)
        updated_state = AppState.from_dict(state.to_dict())
        updated_state.advertisement.fixed_price = price
        self._logger.info(f"Подтянул актуальную цену: {price}")
        return updated_state
