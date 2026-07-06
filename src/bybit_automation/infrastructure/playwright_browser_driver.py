from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from bybit_automation.models.automation_mode import AutomationMode
from bybit_automation.models.merchant_cycle import AdvertisementSnapshot, MerchantSearchResult
from bybit_automation.models.payment_method import PaymentMethodState
from bybit_automation.services.logging_service import AppLogger


class PlaywrightBrowserDriver:
    ADS_URL = "https://www.bybit.com/ru-RU/p2p/merchant-admin/ads"
    SELL_URL = "https://www.bybit.com/ru-RU/p2p/sell/USDT/RUB"
    READY_TIMEOUT_MS = 15_000

    def __init__(
        self,
        logger: AppLogger,
        *,
        mode: str,
        user_data_dir: Path,
        artifacts_dir: Path,
        cdp_endpoint: str | None = None,
        headless: bool = False,
    ) -> None:
        self._logger = logger
        self._mode = mode
        self._user_data_dir = user_data_dir
        self._artifacts_dir = artifacts_dir
        self._cdp_endpoint = cdp_endpoint or os.getenv("BYBIT_PLAYWRIGHT_CDP_ENDPOINT", "")
        self._headless = headless
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._chrome_process: subprocess.Popen | None = None
        self._context: Any | None = None
        self._sell_page: Any | None = None
        self._ads_page: Any | None = None

    def _log(self, message: str) -> None:
        self._logger.info(f"Playwright: {message}")

    def _ensure_context(self) -> Any:
        if self._context is not None:
            return self._context
        if self._mode == AutomationMode.INCOGNITON_PLAYWRIGHT_CDP and not self._cdp_endpoint:
            raise RuntimeError(
                "Режим Incogniton Playwright/CDP требует endpoint в BYBIT_PLAYWRIGHT_CDP_ENDPOINT "
                "например http://127.0.0.1:9222."
            )
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise RuntimeError(
                "Playwright не установлен. Выполни: python -m pip install -e . "
                "и затем python -m playwright install chromium."
            ) from error

        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        if self._mode == AutomationMode.INCOGNITON_PLAYWRIGHT_CDP:
            self._log(f"подключаюсь к CDP endpoint {self._cdp_endpoint}")
            self._browser = self._playwright.chromium.connect_over_cdp(self._cdp_endpoint)
            self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
            return self._context

        self._user_data_dir.mkdir(parents=True, exist_ok=True)
        if self._mode == AutomationMode.PLAYWRIGHT_PROFILE:
            chrome_executable = self._find_chrome_executable()
            if chrome_executable is not None:
                port = self._find_free_port()
                command = self._build_manual_chrome_command(
                    chrome_executable=chrome_executable,
                    remote_debugging_port=port,
                )
                self._log(f"запускаю системный Chrome с профилем: {self._user_data_dir}")
                self._chrome_process = subprocess.Popen(command)
                endpoint = f"http://127.0.0.1:{port}"
                self._browser = self._connect_to_manual_chrome(endpoint)
                self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
                return self._context

        self._log(f"запускаю persistent profile: {self._user_data_dir}")
        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                str(self._user_data_dir),
                **self._launch_persistent_context_kwargs(),
            )
        except Exception as error:
            if self._mode != AutomationMode.PLAYWRIGHT_PROFILE:
                raise
            self._log(f"не удалось запустить системный Chrome, использую Chromium Playwright: {error}")
            fallback_kwargs = self._launch_persistent_context_kwargs(prefer_chrome=False)
            self._context = self._playwright.chromium.launch_persistent_context(
                str(self._user_data_dir),
                **fallback_kwargs,
            )
        return self._context

    def _find_chrome_executable(self) -> Path | None:
        candidates = (
            Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        )
        return next((path for path in candidates if path.exists()), None)

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _build_manual_chrome_command(self, *, chrome_executable: Path, remote_debugging_port: int) -> list[str]:
        return [
            str(chrome_executable),
            f"--remote-debugging-port={remote_debugging_port}",
            f"--user-data-dir={self._user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ]

    def _connect_to_manual_chrome(self, endpoint: str) -> Any:
        last_error: Exception | None = None
        for _ in range(30):
            try:
                return self._playwright.chromium.connect_over_cdp(endpoint)
            except Exception as error:
                last_error = error
                time.sleep(0.2)
        raise RuntimeError(f"Не удалось подключиться к запущенному Chrome по {endpoint}: {last_error}")

    def _launch_persistent_context_kwargs(self, *, prefer_chrome: bool = True) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "headless": self._headless,
            "viewport": {"width": 1440, "height": 1000},
            "locale": "ru-RU",
        }
        if self._mode == AutomationMode.PLAYWRIGHT_PROFILE:
            if prefer_chrome:
                kwargs["channel"] = "chrome"
            kwargs["ignore_default_args"] = [
                "--disable-background-networking",
                "--disable-component-extensions-with-background-pages",
                "--disable-component-update",
                "--disable-extensions",
            ]
        return kwargs

    def open_profile(self, window_title: str) -> None:
        if self._mode == AutomationMode.PLAYWRIGHT_PROFILE:
            self._user_data_dir.mkdir(parents=True, exist_ok=True)
            chrome_executable = self._find_chrome_executable()
            if chrome_executable is None:
                raise RuntimeError("Не найден установленный Google Chrome для открытия Playwright-профиля.")
            port = self._find_free_port()
            command = self._build_manual_chrome_command(
                chrome_executable=chrome_executable,
                remote_debugging_port=port,
            )
            self._log(f"открываю системный Chrome без CDP-подключения: {command}")
            subprocess.Popen(command)
            return
        context = self._ensure_context()
        if context.pages:
            context.pages[0].bring_to_front()
            return
        self._sell_page = self._page_for_url(self.SELL_URL, role="Sell")

    def _page_for_url(self, url: str, *, role: str) -> Any:
        context = self._ensure_context()
        for page in context.pages:
            if self._same_base_url(page.url, url):
                self._log(f"использую существующую вкладку {role}: {page.url}")
                page.bring_to_front()
                page.wait_for_load_state("domcontentloaded", timeout=self.READY_TIMEOUT_MS)
                return page
        page = context.new_page()
        self._log(f"открываю вкладку {role}: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=self.READY_TIMEOUT_MS)
        return page

    def _same_base_url(self, current_url: str, target_url: str) -> bool:
        return current_url.split("?", 1)[0].rstrip("/") == target_url.rstrip("/")

    def _body_text(self, page: Any) -> str:
        page.wait_for_load_state("domcontentloaded", timeout=self.READY_TIMEOUT_MS)
        return page.locator("body").inner_text(timeout=self.READY_TIMEOUT_MS)

    def _save_failure_artifact(self, page: Any, step_name: str) -> None:
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", step_name).strip("_") or "step"
        path = self._artifacts_dir / f"{int(time.time())}-{safe_name}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            self._log(f"сохранён screenshot сбоя: {path}")
        except Exception as error:
            self._log(f"не удалось сохранить screenshot сбоя: {error}")

    def _click_and_expect(
        self,
        page: Any,
        click_action: Callable[[], None],
        expect_action: Callable[[], None],
        *,
        step_name: str,
        expected: str,
    ) -> None:
        try:
            click_action()
            expect_action()
        except Exception as error:
            self._save_failure_artifact(page, step_name)
            raise RuntimeError(f"Шаг '{step_name}' не подтвердился: ожидалось '{expected}'. Причина: {error}") from error

    def focus(self, window_title: str) -> None:
        self._ensure_context()

    def ensure_sell_tab(self, window_title: str) -> None:
        self._sell_page = self._page_for_url(self.SELL_URL, role="Sell")

    def ensure_ads_tab(self, window_title: str) -> None:
        self._ads_page = self._page_for_url(self.ADS_URL, role="Ads")

    def refresh_page(self, window_title: str) -> None:
        page = self._sell_page or self._page_for_url(self.SELL_URL, role="Sell")
        page.reload(wait_until="domcontentloaded", timeout=self.READY_TIMEOUT_MS)

    def read_current_sell_price(self, window_title: str) -> str:
        self.ensure_sell_tab(window_title)
        text = self._body_text(self._sell_page)
        match = re.search(r"\b\d+,\d{2}\s*RUB\b", text)
        if match:
            return match.group().replace("RUB", "").strip()
        match = re.search(r"\b\d+,\d{2}\b", text)
        if match:
            return match.group().strip()
        raise RuntimeError("Не удалось прочитать цену на Sell-странице через Playwright.")

    def read_current_advertisement(self, window_title: str) -> AdvertisementSnapshot | None:
        self.ensure_ads_tab(window_title)
        text = self._body_text(self._ads_page)
        advertisement_id = self._first_match(text, r"\b\d{10,}\b")
        price = self._first_match(text, r"\b\d+,\d{2}\s*RUB\b").replace("RUB", "").strip()
        created_at = self._first_match(text, r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}")
        if not advertisement_id or not price:
            return None
        side = "Покупка" if "Покупка" in text else "Продажа" if "Продажа" in text else ""
        return AdvertisementSnapshot(advertisement_id=advertisement_id, price=price, side=side, created_at=created_at)

    def _first_match(self, text: str, pattern: str) -> str:
        match = re.search(pattern, text)
        return match.group().strip() if match else ""

    def delete_current_advertisement(self, window_title: str) -> None:
        snapshot = self.read_current_advertisement(window_title)
        if snapshot is None:
            self._log("старое объявление не найдено, удалять нечего")
            return
        page = self._ads_page
        row = page.get_by_text(snapshot.advertisement_id, exact=True).locator("xpath=ancestor::*[@role='row' or self::tr][1]")
        delete_button = row.get_by_role("button", name=re.compile("Удал|Delete", re.IGNORECASE)).last()
        if delete_button.count() == 0:
            delete_button = row.locator("button, [role=button]").last()
        self._click_and_expect(
            page,
            lambda: delete_button.click(timeout=self.READY_TIMEOUT_MS),
            lambda: page.get_by_role("button", name=re.compile("Подтверд|Удал|Confirm|Delete", re.IGNORECASE)).first().wait_for(timeout=self.READY_TIMEOUT_MS),
            step_name="delete-open-confirm",
            expected="popup подтверждения удаления",
        )
        confirm = page.get_by_role("button", name=re.compile("Подтверд|Удал|Confirm|Delete", re.IGNORECASE)).first()
        self._click_and_expect(
            page,
            lambda: confirm.click(timeout=self.READY_TIMEOUT_MS),
            lambda: page.get_by_text(snapshot.advertisement_id, exact=True).wait_for(state="detached", timeout=self.READY_TIMEOUT_MS),
            step_name="delete-confirm",
            expected="строка объявления исчезла",
        )

    def collect_all_merchants(self, window_title: str, depth: int) -> list[str]:
        merchants: list[str] = []
        self.ensure_sell_tab(window_title)
        for page_number in range(1, depth + 1):
            if page_number > 1:
                self._open_listing_page(self._sell_page, page_number)
            merchants.extend(self._extract_merchant_candidates(self._body_text(self._sell_page)))
        return merchants

    def search_merchant(
        self,
        window_title: str,
        account_name: str,
        depth: int,
        stop_requested: Callable[[], bool],
        on_progress: Callable[[int, int, str], None],
    ) -> MerchantSearchResult:
        target = self._normalize_merchant_name(account_name)
        self.ensure_sell_tab(window_title)
        for page_number in range(1, depth + 1):
            if stop_requested():
                return MerchantSearchResult(found=False)
            if page_number > 1:
                on_progress(page_number, 0, f"Открываю страницу {page_number}")
                self._open_listing_page(self._sell_page, page_number)
            candidates = self._extract_merchant_candidates(self._body_text(self._sell_page))
            for position, candidate in enumerate(candidates, start=1):
                on_progress(page_number, position, f"Проверяю продавца {position}/10: {candidate}")
                if self._normalize_merchant_name(candidate) == target:
                    on_progress(page_number, position, "Найден")
                    return MerchantSearchResult(found=True, page=page_number, position=position, matched_name=candidate)
        return MerchantSearchResult(found=False)

    def _open_listing_page(self, page: Any, page_number: int) -> None:
        control = page.get_by_role("button", name=str(page_number)).or_(page.get_by_text(str(page_number), exact=True)).first()
        self._click_and_expect(
            page,
            lambda: control.click(timeout=self.READY_TIMEOUT_MS),
            lambda: control.wait_for(timeout=self.READY_TIMEOUT_MS),
            step_name=f"listing-page-{page_number}",
            expected=f"страница листинга {page_number} активна",
        )

    def _extract_merchant_candidates(self, text: str) -> list[str]:
        candidates: list[str] = []
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            normalized = self._normalize_merchant_name(line)
            if not normalized or self._is_non_merchant_text(normalized):
                continue
            if re.search(r"\b\d+\s*(исполнено|orders?|%)\b", line, flags=re.IGNORECASE):
                name = re.split(r"\s+\d+\s*(?:исполнено|orders?|%)\b", line, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                if name:
                    candidates.append(name)
        return candidates

    def _normalize_merchant_name(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s.-]+", " ", text, flags=re.UNICODE)).strip().lower()

    def _is_non_merchant_text(self, normalized: str) -> bool:
        forbidden_parts = (
            "купить монеты",
            "продать монеты",
            "faq",
            "начинающий",
            "продвинутый",
            "мейкер",
            "безопасность",
            "merchant",
            "мерчант",
        )
        return any(part in normalized for part in forbidden_parts)

    def open_standard_p2p_ad_form(self, window_title: str) -> None:
        self.ensure_ads_tab(window_title)
        page = self._ads_page
        open_button = page.get_by_role("button", name=re.compile("Разместить|Post", re.IGNORECASE)).first()
        self._click_and_expect(
            page,
            lambda: open_button.click(timeout=self.READY_TIMEOUT_MS),
            lambda: page.get_by_text(re.compile("Стандартная P2P|Standard P2P", re.IGNORECASE)).first().wait_for(timeout=self.READY_TIMEOUT_MS),
            step_name="open-ad-kind-popup",
            expected="выбор стандартной P2P-торговли",
        )
        option = page.get_by_text(re.compile("Стандартная P2P|Standard P2P", re.IGNORECASE)).first()
        self._click_and_expect(
            page,
            lambda: option.click(timeout=self.READY_TIMEOUT_MS),
            lambda: page.get_by_text(re.compile("Фиксированная|Fixed", re.IGNORECASE)).first().wait_for(timeout=self.READY_TIMEOUT_MS),
            step_name="open-standard-p2p-form",
            expected="форма объявления открыта",
        )

    def select_trade_side(self, window_title: str, trade_side: str) -> None:
        self._click_label_or_role(self._ads_page, trade_side, step_name="select-trade-side")

    def set_fixed_price(self, window_title: str, price: str) -> None:
        self._fill_by_label_patterns(self._ads_page, [r"Фиксированная", r"Fixed"], price, "fixed-price")

    def set_payment_time(self, window_title: str, payment_time: str) -> None:
        page = self._ads_page
        opener = page.get_by_text(re.compile("Длительность оплаты|Payment Time", re.IGNORECASE)).first()
        option_name = "30мин." if payment_time.startswith("30") else "15мин."
        self._click_and_expect(
            page,
            lambda: opener.click(timeout=self.READY_TIMEOUT_MS),
            lambda: page.get_by_text(option_name, exact=True).wait_for(timeout=self.READY_TIMEOUT_MS),
            step_name="open-payment-time",
            expected=f"вариант {option_name}",
        )
        page.get_by_text(option_name, exact=True).click(timeout=self.READY_TIMEOUT_MS)

    def set_total_amount(self, window_title: str, total_amount: str) -> None:
        self._fill_by_label_patterns(self._ads_page, [r"Общее количество", r"Total Amount"], total_amount, "total-amount")

    def set_minimum_transaction(self, window_title: str, minimum_transaction: str) -> None:
        self._fill_by_label_patterns(self._ads_page, [r"Мин.*сумма", r"Minimum"], minimum_transaction, "minimum-transaction")

    def set_maximum_transaction(self, window_title: str, maximum_transaction: str) -> None:
        self._fill_by_label_patterns(self._ads_page, [r"Макс.*сумма", r"Maximum"], maximum_transaction, "maximum-transaction")

    def set_notes(self, window_title: str, notes: str) -> None:
        self._fill_by_label_patterns(self._ads_page, [r"Примечания", r"Terms", r"Remarks"], notes, "notes")

    def _fill_by_label_patterns(self, page: Any, labels: list[str], value: str, step_name: str) -> None:
        last_error: Exception | None = None
        for label in labels:
            try:
                field = page.get_by_label(re.compile(label, re.IGNORECASE)).first()
                field.fill(value, timeout=self.READY_TIMEOUT_MS)
                return
            except Exception as error:
                last_error = error
        self._save_failure_artifact(page, step_name)
        raise RuntimeError(f"Не найдено поле для шага '{step_name}'. Последняя ошибка: {last_error}")

    def ensure_counterparty_requirements(self, window_title: str, *, phone_linked: bool, email_linked: bool) -> None:
        if not phone_linked and not email_linked:
            return
        page = self._ads_page
        self._click_label_or_role(page, "Добавить", step_name="open-counterparty-requirements")
        if phone_linked:
            self._set_checkbox_by_text(page, re.compile("телефон|phone", re.IGNORECASE), True)
        if email_linked:
            self._set_checkbox_by_text(page, re.compile("почт|email", re.IGNORECASE), True)
        self._click_label_or_role(page, "Подтверд", step_name="confirm-counterparty-requirements")

    def ensure_payment_methods(self, window_title: str, methods: PaymentMethodState) -> None:
        requested = {
            "Bank Transfer": methods.bank_transfer,
            "Mobile Top-up": methods.mobile_top_up,
            "Cash Deposit to Bank": methods.cash_deposit,
        }
        wanted = [name for name, enabled in requested.items() if enabled]
        if not wanted:
            return
        page = self._ads_page
        self._click_label_or_role(page, "способами оплаты", step_name="open-payment-methods")
        for name in wanted:
            self._set_checkbox_by_text(page, re.compile(re.escape(name), re.IGNORECASE), True)
        self._click_label_or_role(page, "Подтверд", step_name="confirm-payment-methods")

    def _set_checkbox_by_text(self, page: Any, pattern: re.Pattern[str], checked: bool) -> None:
        checkbox = page.get_by_role("checkbox", name=pattern).first()
        if checked:
            checkbox.check(timeout=self.READY_TIMEOUT_MS)
        else:
            checkbox.uncheck(timeout=self.READY_TIMEOUT_MS)

    def accept_terms(self, window_title: str) -> None:
        page = self._ads_page
        checkbox = page.get_by_role("checkbox", name=re.compile("прочитал|соглаша|agree", re.IGNORECASE)).first()
        checkbox.check(timeout=self.READY_TIMEOUT_MS)

    def submit_advertisement(self, window_title: str) -> None:
        self._click_label_or_role(self._ads_page, "Разместить объявления", step_name="submit-advertisement")

    def enter_security_password(self, window_title: str, password: str) -> None:
        page = self._ads_page
        self._fill_by_label_patterns(page, [r"Финансовый пароль", r"Fund Password"], password, "security-password")
        self._click_label_or_role(page, "Подтвердить", step_name="confirm-security-password")

    def _click_label_or_role(self, page: Any, text: str, *, step_name: str) -> None:
        pattern = re.compile(re.escape(text), re.IGNORECASE)
        target = page.get_by_role("button", name=pattern).or_(page.get_by_text(pattern)).first()
        self._click_and_expect(
            page,
            lambda: target.click(timeout=self.READY_TIMEOUT_MS),
            lambda: page.wait_for_load_state("domcontentloaded", timeout=self.READY_TIMEOUT_MS),
            step_name=step_name,
            expected=f"шаг после клика '{text}' доступен",
        )

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        if self._chrome_process is not None and self._chrome_process.poll() is None:
            self._chrome_process.terminate()
