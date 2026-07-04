from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from bybit_automation.infrastructure.existing_browser_window_driver import PaymentMethodState
from bybit_automation.models.app_state import AppState
from bybit_automation.models.merchant_cycle import AdvertisementSnapshot, MerchantSearchResult
from bybit_automation.services.logging_service import AppLogger


class BrowserDriver(Protocol):
    def focus(self, window_title: str) -> None: ...
    def ensure_sell_tab(self, window_title: str) -> None: ...
    def refresh_page(self, window_title: str) -> None: ...
    def read_current_sell_price(self, window_title: str) -> str: ...
    def ensure_ads_tab(self, window_title: str) -> None: ...
    def read_current_advertisement(self, window_title: str) -> AdvertisementSnapshot | None: ...
    def delete_current_advertisement(self, window_title: str) -> None: ...
    def collect_all_merchants(self, window_title: str, depth: int) -> list[str]: ...
    def search_merchant(
        self,
        window_title: str,
        account_name: str,
        depth: int,
        stop_requested: Callable[[], bool],
        on_progress: Callable[[int, int, str], None],
    ) -> MerchantSearchResult: ...
    def open_standard_p2p_ad_form(self, window_title: str) -> None: ...
    def select_trade_side(self, window_title: str, trade_side: str) -> None: ...
    def set_fixed_price(self, window_title: str, price: str) -> None: ...
    def set_payment_time(self, window_title: str, payment_time: str) -> None: ...
    def set_total_amount(self, window_title: str, total_amount: str) -> None: ...
    def set_minimum_transaction(self, window_title: str, minimum_transaction: str) -> None: ...
    def set_maximum_transaction(self, window_title: str, maximum_transaction: str) -> None: ...
    def set_notes(self, window_title: str, notes: str) -> None: ...
    def ensure_counterparty_requirements(self, window_title: str, *, phone_linked: bool, email_linked: bool) -> None: ...
    def ensure_payment_methods(self, window_title: str, methods: PaymentMethodState) -> None: ...
    def accept_terms(self, window_title: str) -> None: ...
    def submit_advertisement(self, window_title: str) -> None: ...
    def enter_security_password(self, window_title: str, password: str) -> None: ...
    def sleep(self, seconds: float) -> None: ...


@dataclass
class BybitExistingBrowserService:
    driver: BrowserDriver
    logger: AppLogger

    @staticmethod
    def _describe_error(error: Exception) -> str:
        message = str(error).strip()
        if not message or message == "None":
            return repr(error)
        return message

    def fetch_current_price(self, window_title: str) -> str:
        window_title = window_title.strip()
        if not window_title:
            raise RuntimeError("Сначала нужно определить рабочее окно браузера.")
        self.driver.focus(window_title)
        self.logger.info("Активирую рабочую вкладку Sell USDT/RUB.")
        self.driver.ensure_sell_tab(window_title)
        self.logger.info("Обновляю страницу Sell USDT/RUB перед чтением цены.")
        self.driver.refresh_page(window_title)
        self.logger.info("Читаю актуальную цену из рабочей Sell-вкладки.")
        return self.driver.read_current_sell_price(window_title)

    def _prepare_fresh_price_for_new_advertisement(self, state: AppState) -> None:
        window_title = state.browser.window_title.strip()
        self.logger.info("Подтягиваю актуальную цену с первой вкладки перед созданием объявления.")
        try:
            fresh_price = self.fetch_current_price(window_title)
        except (RuntimeError, KeyError) as error:
            message = f"Не удалось подтянуть актуальную цену перед созданием объявления: {error}"
            self.logger.info(message)
            raise RuntimeError(message) from error

        state.advertisement.fixed_price = fresh_price
        self.logger.info(f"Подтянул актуальную цену: {fresh_price}")
        self.logger.info("Возвращаюсь на вторую рабочую вкладку Ads для продолжения.")
        self.driver.focus(window_title)
        self.driver.ensure_ads_tab(window_title)

    def collect_all_merchants(self, window_title: str, depth: int) -> list[str]:
        window_title = window_title.strip()
        if not window_title:
            raise RuntimeError("Сначала нужно определить рабочее окно браузера.")
        self.logger.info(f"Собираю мерчантов: глубина {depth} страниц.")
        last_error: Exception | None = None
        merchants: list[str] | None = None
        for attempt in range(1, 4):
            try:
                self.driver.focus(window_title)
                self.driver.ensure_sell_tab(window_title)
                merchants = self.driver.collect_all_merchants(window_title, depth)
                break
            except Exception as error:
                last_error = error
                if attempt < 3:
                    self.logger.info(
                        f"Сбой сбора мерчантов, повторяю попытку {attempt}/3: {self._describe_error(error)}"
                    )
                    self.driver.sleep(0.5)
                    continue
        if merchants is None:
            detail = self._describe_error(last_error) if last_error is not None else "неизвестная ошибка"
            message = f"Сбор мерчантов сорвался после 3 попыток: {detail}"
            self.logger.info(message)
            raise RuntimeError(message)
        self.logger.info(f"Собрано мерчантов: {len(merchants)}")
        return merchants

    def read_current_advertisement(self, window_title: str) -> AdvertisementSnapshot | None:
        self.driver.focus(window_title)
        self.driver.ensure_ads_tab(window_title)
        return self.driver.read_current_advertisement(window_title)

    def _safe_read_current_advertisement(
        self,
        window_title: str,
        *,
        attempts: int = 3,
        retry_delay_seconds: float = 0.3,
        retry_context: str = "чтение объявления",
    ) -> AdvertisementSnapshot | None:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self.read_current_advertisement(window_title)
            except Exception as error:
                last_error = error
                if attempt < attempts:
                    self.logger.info(
                        f"Сбой UIA при '{retry_context}', повторяю попытку {attempt}/{attempts}: {self._describe_error(error)}"
                    )
                    self.driver.sleep(retry_delay_seconds)
                    continue
        detail = self._describe_error(last_error) if last_error is not None else "неизвестная ошибка"
        raise RuntimeError(f"Не удалось выполнить '{retry_context}': {detail}")

    def delete_current_advertisement(self, window_title: str) -> None:
        self.driver.focus(window_title)
        self.driver.ensure_ads_tab(window_title)
        self.driver.delete_current_advertisement(window_title)

    def _is_missing_delete_button_error(self, error: RuntimeError) -> bool:
        message = str(error).lower()
        return "кноп" in message and "удален" in message

    def _delete_existing_advertisement_before_create(self, window_title: str) -> None:
        current_advertisement = self._safe_read_current_advertisement(
            window_title,
            retry_context="чтение текущего объявления перед удалением",
        )
        if current_advertisement is None:
            self.logger.info("Старое объявление не найдено, создаю новое.")
            return
        try:
            self.logger.info(
                f"Удаляю старое объявление {current_advertisement.advertisement_id} перед созданием нового."
            )
            self.driver.delete_current_advertisement(window_title)
        except (RuntimeError, KeyError) as error:
            if isinstance(error, KeyError) or not self._is_missing_delete_button_error(error):
                raise
            self.logger.info(f"{error} Продолжаю создание нового объявления без лишних кликов.")

    def _wait_for_created_advertisement(self, window_title: str) -> AdvertisementSnapshot:
        attempts = 10
        for attempt in range(1, attempts + 1):
            try:
                snapshot = self._safe_read_current_advertisement(
                    window_title,
                    retry_context="чтение созданного объявления после размещения",
                )
            except (RuntimeError, KeyError) as error:
                if attempt < attempts:
                    self.logger.info(
                        f"Ожидаю появления созданного объявления на вкладке Ads: попытка {attempt}/{attempts}. "
                        f"Причина: {self._describe_error(error)}"
                    )
                    self.driver.sleep(0.5)
                    continue
                raise RuntimeError(f"Не удалось дождаться созданного объявления после {attempts} попыток: {self._describe_error(error)}") from error
            if snapshot is not None:
                return snapshot
            if attempt < attempts:
                self.logger.info(
                    f"Ожидаю появления созданного объявления на вкладке Ads: попытка {attempt}/{attempts}."
                )
                self.driver.sleep(0.5)
        message = "Не удалось дождаться появления созданного объявления на вкладке Ads."
        self.logger.info(message)
        raise RuntimeError(message)

    def create_advertisement(self, state: AppState) -> AdvertisementSnapshot:
        started = self.fill_advertisement_form(state)
        if not started:
            raise RuntimeError("Не удалось начать создание объявления.")
        return self._wait_for_created_advertisement(state.browser.window_title)

    def search_merchant(
        self,
        window_title: str,
        account_name: str,
        depth: int,
        stop_requested: Callable[[], bool],
        on_progress: Callable[[int, int, str], None],
    ) -> MerchantSearchResult:
        self.logger.info(f"Поиск аккаунта: активирую окно браузера '{window_title}'.")
        self.driver.focus(window_title)
        self.logger.info("Поиск аккаунта: открываю вкладку Sell USDT/RUB.")
        self.driver.ensure_sell_tab(window_title)
        self.logger.info(f"Поиск аккаунта: ищу '{account_name}' на глубине {depth} страниц.")
        result = self.driver.search_merchant(window_title, account_name, depth, stop_requested, on_progress)
        if result.found:
            self.logger.info(
                f"Поиск аккаунта: найден на странице {result.page}, позиция {result.position}/10."
            )
        else:
            self.logger.info("Поиск аккаунта: аккаунт не найден на заданной глубине.")
        return result

    def fill_advertisement_form(self, state: AppState) -> bool:
        window_title = state.browser.window_title.strip()
        if not window_title:
            self.logger.info("Сначала нажми 'Проверить браузер', чтобы выбрать рабочее окно.")
            return False

        self.logger.info(f"Работаю с открытым окном профиля: {window_title}")
        self.driver.focus(window_title)
        self._prepare_fresh_price_for_new_advertisement(state)
        self._delete_existing_advertisement_before_create(window_title)
        self.logger.info("Открываю popup размещения объявления.")
        self.driver.open_standard_p2p_ad_form(window_title)
        self.logger.info("Открыл форму размещения объявления из Ads-вкладки.")

        self.driver.select_trade_side(window_title, state.advertisement.trade_side)
        self.logger.info(f"Выбран тип объявления: {state.advertisement.trade_side}")

        self.driver.set_fixed_price(window_title, state.advertisement.fixed_price)
        self.logger.info("Заполнил фиксированную цену.")

        self.driver.set_payment_time(window_title, state.advertisement.payment_time)
        self.logger.info(f"Установил время оплаты: {state.advertisement.payment_time}")

        self.driver.set_total_amount(window_title, state.advertisement.total_amount)
        self.driver.set_minimum_transaction(window_title, state.advertisement.minimum_transaction)
        self.driver.set_maximum_transaction(window_title, state.advertisement.maximum_transaction)
        self.logger.info("Заполнил количество и лимиты.")

        self.driver.ensure_counterparty_requirements(
            window_title,
            phone_linked=state.advertisement.phone_linked,
            email_linked=state.advertisement.email_linked,
        )
        self.logger.info("Проверил требования к контрагенту.")

        self.driver.set_notes(window_title, state.advertisement.notes)
        self.logger.info("Заполнил примечание.")

        self.driver.ensure_payment_methods(
            window_title,
            PaymentMethodState(
                bank_transfer=state.advertisement.payment_bank_transfer,
                mobile_top_up=state.advertisement.payment_mobile_top_up,
                cash_deposit=state.advertisement.payment_cash_deposit,
            ),
        )
        self.logger.info("Проверил способы оплаты.")

        self.driver.accept_terms(window_title)
        self.logger.info("Подтвердил согласие с условиями.")

        self.driver.submit_advertisement(window_title)
        self.logger.info("Нажал кнопку размещения объявления.")

        self.driver.enter_security_password(window_title, state.advertisement.security_password)
        self.logger.info("Ввел пароль безопасности.")
        return True
