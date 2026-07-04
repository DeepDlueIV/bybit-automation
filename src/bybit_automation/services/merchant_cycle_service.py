from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from bybit_automation.models.app_state import AdvertisementSettings, AppState, SearchSettings
from bybit_automation.models.merchant_cycle import (
    AdvertisementSnapshot,
    MerchantCycleResult,
    MerchantSearchResult,
)
from bybit_automation.services.logging_service import AppLogger


class BybitGateway(Protocol):
    def read_current_advertisement(self, window_title: str | None = None) -> AdvertisementSnapshot | None:
        ...

    def delete_advertisement(self, advertisement_id: str) -> None:
        ...

    def create_advertisement(self, settings: AdvertisementSettings) -> AdvertisementSnapshot:
        ...

    def search_merchant(self, account_name: str, depth: int, max_pages: int = 2) -> MerchantSearchResult:
        ...


class LiveBybitGateway(Protocol):
    def read_current_advertisement(self, window_title: str) -> AdvertisementSnapshot | None:
        ...

    def delete_current_advertisement(self, window_title: str) -> None:
        ...

    def fetch_current_price(self, window_title: str) -> str:
        ...

    def create_advertisement(self, state: AppState) -> AdvertisementSnapshot:
        ...

    def search_merchant(
        self,
        window_title: str,
        account_name: str,
        depth: int,
        stop_requested: Callable[[], bool],
        on_progress: Callable[[int, int, str], None],
    ) -> MerchantSearchResult:
        ...


class PositionSoundNotifier(Protocol):
    def notify_if_top_position(self, position: int) -> None:
        ...


@dataclass
class MerchantCycleService:
    gateway: BybitGateway | LiveBybitGateway
    logger: AppLogger
    found_accounts_file: Path | None = None
    position_sound_notifier: PositionSoundNotifier | None = None
    _stop_requested: bool = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run_cycle(
        self,
        advertisement: AdvertisementSettings,
        search: SearchSettings,
        *,
        max_attempts: int = 3,
    ) -> MerchantCycleResult:
        account_name = search.account_name.strip()
        depth = int(search.depth or "0")
        current_ad = self.gateway.read_current_advertisement()  # type: ignore[call-arg]

        initial_search = self.gateway.search_merchant(account_name, depth, max_pages=2)  # type: ignore[call-arg]
        if initial_search.found and current_ad is not None:
            return self._success_result(current_ad, initial_search, 0)

        for attempt in range(1, max_attempts + 1):
            if current_ad is not None:
                self.logger.info(f"Удаляю объявление {current_ad.advertisement_id}.")
                self.gateway.delete_advertisement(current_ad.advertisement_id)  # type: ignore[attr-defined]

            self.logger.info(f"Создаю объявление. Попытка {attempt}.")
            current_ad = self.gateway.create_advertisement(advertisement)  # type: ignore[call-arg]

            search_result = self.gateway.search_merchant(account_name, depth, max_pages=2)  # type: ignore[call-arg]
            if search_result.found:
                return self._success_result(current_ad, search_result, attempt)

        message = f"Аккаунт {account_name or 'без имени'} не найден после {max_attempts} попыток."
        self.logger.info(message)
        return MerchantCycleResult(success=False, stopped=False, attempts=max_attempts, message=message)

    def run_live_cycle(
        self,
        state: AppState,
        *,
        stop_requested: Callable[[], bool],
        on_progress: Callable[[int, int, str], None],
    ) -> MerchantCycleResult:
        self._stop_requested = False
        window_title = state.browser.window_title.strip()
        account_name = state.search.account_name.strip()
        depth = int(state.search.depth or "0")
        if not window_title:
            raise RuntimeError("Сначала нужно определить рабочее окно браузера.")
        if not account_name:
            raise RuntimeError("Укажи имя аккаунта для поиска.")
        if depth < 1:
            raise RuntimeError("Глубина поиска должна быть не меньше 1.")

        self.logger.info(f"Запускаю цикл поиска аккаунта '{account_name}' на глубине {depth} страниц.")
        attempts = 0
        while True:
            if self._should_stop(stop_requested):
                return self._stopped_result()

            self.logger.info("Читаю текущее объявление перед поиском.")
            current_ad = self.gateway.read_current_advertisement(window_title)  # type: ignore[call-arg]
            if current_ad is None:
                self.logger.info("Текущее объявление не найдено.")
            else:
                self.logger.info(f"Текущее объявление: id {current_ad.advertisement_id}, цена {current_ad.price}.")

            self.logger.info("Запускаю поиск аккаунта в листинге продавцов.")
            search_result = self.gateway.search_merchant(  # type: ignore[call-arg]
                window_title,
                account_name,
                depth,
                self._stop_requested_callback(stop_requested),
                on_progress,
            )
            if search_result.found and current_ad is not None:
                self.logger.info("Аккаунт найден, цикл завершён успешно.")
                result = self._success_result(current_ad, search_result, attempts)
                self._append_found_account(result)
                return result
            if search_result.found:
                self.logger.info("Аккаунт найден, но текущее объявление не прочитано. Продолжаю цикл создания объявления.")
            else:
                self.logger.info("Аккаунт не найден, перехожу к пересозданию объявления.")

            if self._should_stop(stop_requested):
                return self._stopped_result()

            if current_ad is not None:
                self._delete_current_live_advertisement(window_title, current_ad)

            if self._should_stop(stop_requested):
                return self._stopped_result()

            updated_state = AppState.from_dict(state.to_dict())
            self.logger.info("Читаю актуальную цену перед созданием нового объявления.")
            fresh_price = self.gateway.fetch_current_price(window_title)  # type: ignore[attr-defined]
            updated_state.advertisement.fixed_price = fresh_price
            self.logger.info(f"Подтянул актуальную цену: {fresh_price}")

            self.logger.info("Создаю новое объявление после удаления старого.")
            current_ad = self.gateway.create_advertisement(updated_state)  # type: ignore[call-arg]
            self.logger.info(f"Новое объявление создано: id {current_ad.advertisement_id}, цена {current_ad.price}.")
            attempts += 1
            state = updated_state

    def _stop_requested_callback(self, stop_requested: Callable[[], bool]) -> Callable[[], bool]:
        return lambda: self._should_stop(stop_requested)

    def _is_missing_delete_button_error(self, error: Exception) -> bool:
        message = str(error).lower()
        return "кноп" in message and "удален" in message

    def _delete_current_live_advertisement(self, window_title: str, advertisement: AdvertisementSnapshot) -> None:
        self.logger.info(f"Удаляю объявление {advertisement.advertisement_id}.")
        try:
            self.gateway.delete_current_advertisement(window_title)  # type: ignore[attr-defined]
        except (RuntimeError, KeyError) as error:
            if isinstance(error, KeyError) or not self._is_missing_delete_button_error(error):
                raise
            self.logger.info(f"{error} Продолжаю цикл без лишних кликов.")

    def _should_stop(self, stop_requested: Callable[[], bool]) -> bool:
        return self._stop_requested or stop_requested()

    def _stopped_result(self) -> MerchantCycleResult:
        message = "Поиск остановлен."
        self.logger.info(message)
        return MerchantCycleResult(success=False, stopped=True, attempts=0, message=message)

    def _append_found_account(self, result: MerchantCycleResult) -> None:
        if self.found_accounts_file is None:
            return
        self.found_accounts_file.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"страница {result.page}",
            f"строка {result.position}/10",
            f"id {result.advertisement_id}",
            f"цена {result.price}",
        ]
        if result.advertisement_created_at:
            lines.append(f"дата объявления {result.advertisement_created_at}")
        block = "\n".join([*lines, ""])
        with self.found_accounts_file.open("a", encoding="utf-8") as handle:
            handle.write(block)

    def _success_result(
        self,
        advertisement: AdvertisementSnapshot,
        search_result: MerchantSearchResult,
        attempts: int,
    ) -> MerchantCycleResult:
        self.logger.info(f"страница {search_result.page}")
        self.logger.info(f"строка {search_result.position}/10")
        self.logger.info(f"id {advertisement.advertisement_id}")
        self.logger.info(f"цена {advertisement.price}")
        if advertisement.created_at:
            self.logger.info(f"дата объявления {advertisement.created_at}")
        absolute_position = ((search_result.page - 1) * 10) + search_result.position
        if self.position_sound_notifier is not None and 1 <= absolute_position <= 10:
            self.position_sound_notifier.notify_if_top_position(absolute_position)
        message = "Аккаунт найден"
        return MerchantCycleResult(
            success=True,
            stopped=False,
            attempts=attempts,
            message=message,
            advertisement_id=advertisement.advertisement_id,
            price=advertisement.price,
            advertisement_created_at=advertisement.created_at,
            page=search_result.page,
            position=search_result.position,
        )
