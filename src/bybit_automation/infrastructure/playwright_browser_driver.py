from __future__ import annotations

import json
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
                port = self._find_existing_debug_port()
                if port is None:
                    port = self._find_free_port()
                    command = self._build_manual_chrome_command(
                        chrome_executable=chrome_executable,
                        remote_debugging_port=port,
                    )
                    self._log(f"запускаю системный Chrome с профилем: {self._user_data_dir}")
                    self._log(f"аргументы запуска Chrome: {command}")
                    self._chrome_process = subprocess.Popen(command)
                else:
                    self._log(f"подключаюсь к уже открытому Chrome с профилем на порту {port}")
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

    def _iter_chrome_command_lines(self) -> list[str]:
        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like '*chrome.exe' } | ForEach-Object { $_.CommandLine }",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except Exception:
            return []
        return [line.strip() for line in completed.stdout.splitlines() if line.strip()]

    def _find_existing_debug_port(self) -> int | None:
        profile = str(self._user_data_dir).lower()
        for command_line in self._iter_chrome_command_lines():
            normalized = command_line.lower()
            if profile not in normalized:
                continue
            match = re.search(r"--remote-debugging-port=(\d+)", command_line)
            if match:
                return int(match.group(1))
        return None

    def _connect_to_manual_chrome(self, endpoint: str) -> Any:
        last_error: Exception | None = None
        for _ in range(30):
            try:
                return self._playwright.chromium.connect_over_cdp(endpoint, timeout=5_000)
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
                self._wait_for_domcontentloaded_best_effort(page, role=role)
                return page
        page = context.new_page()
        self._log(f"открываю вкладку {role}: {url}")
        page.goto(url, wait_until="commit", timeout=self.READY_TIMEOUT_MS)
        self._wait_for_domcontentloaded_best_effort(page, role=role)
        return page

    def _same_base_url(self, current_url: str, target_url: str) -> bool:
        return current_url.split("?", 1)[0].rstrip("/") == target_url.rstrip("/")

    def _wait_for_domcontentloaded_best_effort(self, page: Any, *, role: str) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=self.READY_TIMEOUT_MS)
        except Exception as error:
            self._log(f"вкладка {role}: domcontentloaded не дождались, продолжаю по DOM: {error}")

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
        return self._wait_for_sell_price(window_title)

    def _wait_for_sell_price(self, window_title: str) -> str:
        deadline = time.monotonic() + 45
        last_candidates: list[str] = []
        while time.monotonic() < deadline:
            text = self._body_text(self._sell_page)
            last_candidates = self._extract_price_candidates(text)
            price = self._select_sell_price(last_candidates)
            if price:
                return price
            time.sleep(0.3)
        report_path = self.diagnose_sell_page(window_title)
        raise RuntimeError(
            "Не удалось прочитать цену на Sell-странице через Playwright. "
            f"Последние кандидаты: {last_candidates}. Диагностика: {report_path}"
        )

    def diagnose_sell_page(self, window_title: str) -> Path:
        self.ensure_sell_tab(window_title)
        page = self._sell_page
        text = self._body_text(page)
        price_candidates = self._extract_price_candidates(text)
        timestamp = int(time.time())
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = self._artifacts_dir / f"{timestamp}-sell-diagnostics.png"
        report_path = self._artifacts_dir / f"{timestamp}-sell-diagnostics.json"
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception as error:
            self._log(f"не удалось сохранить screenshot Sell-диагностики: {error}")
            screenshot_path = Path("")
        payload = {
            "url": page.url,
            "title": page.title(),
            "price_candidates": price_candidates,
            "screenshot": str(screenshot_path) if screenshot_path else "",
            "body_text": text,
        }
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log(
            f"Sell-диагностика сохранена: {report_path}; кандидаты цен: {price_candidates[:10]}"
        )
        return report_path

    def diagnose_ads_page(self, window_title: str) -> Path:
        self.ensure_ads_tab(window_title)
        page = self._ads_page
        text = self._body_text(page)
        candidates = self._extract_advertisement_candidates(text)
        timestamp = int(time.time())
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = self._artifacts_dir / f"{timestamp}-ads-diagnostics.png"
        report_path = self._artifacts_dir / f"{timestamp}-ads-diagnostics.json"
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception as error:
            self._log(f"не удалось сохранить screenshot Ads-диагностики: {error}")
            screenshot_path = Path("")
        payload = {
            "url": page.url,
            "title": page.title(),
            "advertisement_candidates": candidates,
            "screenshot": str(screenshot_path) if screenshot_path else "",
            "body_text": text,
        }
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log(f"Ads-диагностика сохранена: {report_path}; кандидаты: {candidates}")
        return report_path

    def _extract_price_candidates(self, text: str) -> list[str]:
        candidates: list[str] = []
        patterns = [
            r"\b\d+(?:[ .]\d{3})*,\d{2}\s*RUB\b",
            r"\b\d+(?:[ .]\d{3})*,\d{2}\b",
            r"(?<![,.\d])\b\d+(?:\.\d{2})?\s*RUB\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                value = re.sub(r"\s+", " ", match.group()).strip()
                if any(value == candidate or value in candidate for candidate in candidates):
                    continue
                candidates = [candidate for candidate in candidates if candidate not in value]
                candidates.append(value)
        return candidates

    def _select_sell_price(self, candidates: list[str]) -> str:
        for candidate in candidates:
            if "rub" not in candidate.lower():
                continue
            value = candidate.lower().replace("rub", "").strip()
            value = value.replace("\u00a0", "").replace(" ", "")
            try:
                numeric = float(value.replace(",", "."))
            except ValueError:
                continue
            if numeric > 0:
                return value
        return ""

    def _extract_advertisement_candidates(self, text: str) -> dict[str, list[str]]:
        return {
            "advertisement_ids": self._unique_matches(text, r"\b\d{10,}\b"),
            "prices": self._extract_price_candidates(text),
            "created_at": self._unique_matches(text, r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}"),
        }

    def _unique_matches(self, text: str, pattern: str) -> list[str]:
        values: list[str] = []
        for match in re.finditer(pattern, text):
            value = match.group().strip()
            if value not in values:
                values.append(value)
        return values

    def read_current_advertisement(self, window_title: str) -> AdvertisementSnapshot | None:
        self.ensure_ads_tab(window_title)
        text = self._body_text(self._ads_page)
        return self._extract_advertisement_snapshot_from_text(text)

    def _extract_advertisement_snapshot_from_text(self, text: str) -> AdvertisementSnapshot | None:
        advertisement_id = self._first_match(text, r"\b\d{10,}\b")
        price = self._extract_advertisement_listing_price(text)
        created_at = self._first_match(text, r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}")
        if not advertisement_id or not price:
            return None
        side = "Покупка" if "Покупка" in text else "Продажа" if "Продажа" in text else ""
        return AdvertisementSnapshot(advertisement_id=advertisement_id, price=price, side=side, created_at=created_at)

    def _extract_advertisement_listing_price(self, text: str) -> str:
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if "RUB" not in line.upper() or "-" in line:
                continue
            match = re.search(r"\b\d+(?:[ \u00a0]\d{3})*,\d{2}\s*RUB\b|\b\d+,\d{2}\s*RUB\b", line, re.IGNORECASE)
            if match:
                return match.group().replace("RUB", "").replace("\u00a0", " ").strip()
        return ""

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
            lambda: page.get_by_role("button", name=re.compile("Подтверд|Удал|Confirm|Delete", re.IGNORECASE)).first.wait_for(timeout=self.READY_TIMEOUT_MS),
            step_name="delete-open-confirm",
            expected="popup подтверждения удаления",
        )
        confirm = page.get_by_role("button", name=re.compile("Подтверд|Удал|Confirm|Delete", re.IGNORECASE)).first
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
        control = page.get_by_role("button", name=str(page_number)).or_(page.get_by_text(str(page_number), exact=True)).first
        self._click_and_expect(
            page,
            lambda: control.click(timeout=self.READY_TIMEOUT_MS),
            lambda: control.wait_for(timeout=self.READY_TIMEOUT_MS),
            step_name=f"listing-page-{page_number}",
            expected=f"страница листинга {page_number} активна",
        )

    def _extract_merchant_candidates(self, text: str) -> list[str]:
        candidates: list[str] = []
        lines = [re.sub(r"\s+", " ", raw_line).strip() for raw_line in text.splitlines()]
        for index, line in enumerate(lines):
            normalized = self._normalize_merchant_name(line)
            if not normalized or self._is_non_merchant_text(normalized):
                continue
            stats_match = re.search(r"\b\d+\s*(исполнено|orders?|%)\b", line, flags=re.IGNORECASE)
            if stats_match:
                name = line[: stats_match.start()].strip()
                if not name:
                    name = self._merchant_name_before_stats(lines, index)
                if name:
                    candidates.append(name)
        return candidates

    def _merchant_name_before_stats(self, lines: list[str], stats_index: int) -> str:
        for candidate in reversed(lines[max(0, stats_index - 3) : stats_index]):
            cleaned = re.sub(r"\s+", " ", re.sub(r"[^\w\s.-]+", " ", candidate, flags=re.UNICODE)).strip()
            normalized = self._normalize_merchant_name(cleaned)
            if normalized and not self._is_non_merchant_text(normalized):
                return cleaned
        return ""

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
        option = page.get_by_text(re.compile("Стандартная P2P|Standard P2P", re.IGNORECASE)).first
        try:
            # Если предыдущая попытка уже открыла модалку, не кликаем кнопку под overlay повторно.
            option.wait_for(timeout=1_000)
        except Exception:
            open_button = page.get_by_text(re.compile("Разместить объяв|Post", re.IGNORECASE)).first
            self._click_and_expect(
                page,
                lambda: open_button.click(timeout=self.READY_TIMEOUT_MS),
                lambda: option.wait_for(timeout=self.READY_TIMEOUT_MS),
                step_name="open-ad-kind-popup",
                expected="выбор стандартной P2P-торговли",
            )
        self._click_and_expect(
            page,
            lambda: option.click(timeout=self.READY_TIMEOUT_MS),
            lambda: page.get_by_text(re.compile("Фиксированная|Fixed", re.IGNORECASE)).first.wait_for(timeout=self.READY_TIMEOUT_MS),
            step_name="open-standard-p2p-form",
            expected="форма объявления открыта",
        )

    def select_trade_side(self, window_title: str, trade_side: str) -> None:
        self._dismiss_payment_modal_if_open(self._ads_page)
        button = self._ads_page.locator("button").filter(has_text=re.compile(f"^{re.escape(trade_side)}$", re.IGNORECASE)).first
        self._click_and_expect(
            self._ads_page,
            lambda: button.click(timeout=self.READY_TIMEOUT_MS),
            lambda: button.wait_for(timeout=self.READY_TIMEOUT_MS),
            step_name="select-trade-side",
            expected=f"выбран тип объявления '{trade_side}'",
        )

    def set_fixed_price(self, window_title: str, price: str) -> None:
        field = self._ads_page.locator('input[placeholder*="Фиксированная цена"], input[placeholder*="Fixed"]').first
        field.fill(price, timeout=self.READY_TIMEOUT_MS)

    def set_payment_time(self, window_title: str, payment_time: str) -> None:
        page = self._ads_page
        option_name = "30мин." if payment_time.startswith("30") else "15мин."
        body_text = self._body_text(page)
        current_match = re.search(r"Длительность оплаты\s+(15мин\.|30мин\.)", body_text)
        current_option = current_match.group(1) if current_match else ""
        if current_option == option_name:
            return
        opener_name = current_option or ("15мин." if "15мин." in body_text else "30мин.")
        opener = page.get_by_text(opener_name, exact=True).first
        self._click_and_expect(
            page,
            lambda: opener.click(timeout=self.READY_TIMEOUT_MS),
            lambda: page.get_by_text(option_name, exact=True).wait_for(timeout=self.READY_TIMEOUT_MS),
            step_name="open-payment-time",
            expected=f"вариант {option_name}",
        )
        page.get_by_text(option_name, exact=True).last.click(timeout=self.READY_TIMEOUT_MS)

    def set_total_amount(self, window_title: str, total_amount: str) -> None:
        self._ads_page.locator('input[placeholder="Ввести"], input[placeholder="Enter"]').first.fill(
            total_amount,
            timeout=self.READY_TIMEOUT_MS,
        )

    def set_minimum_transaction(self, window_title: str, minimum_transaction: str) -> None:
        self._ads_page.locator('input[placeholder="500"]').first.fill(
            minimum_transaction,
            timeout=self.READY_TIMEOUT_MS,
        )

    def set_maximum_transaction(self, window_title: str, maximum_transaction: str) -> None:
        self._ads_page.locator('input[placeholder*="3"], input[placeholder*="500"]').last.fill(
            maximum_transaction,
            timeout=self.READY_TIMEOUT_MS,
        )

    def set_notes(self, window_title: str, notes: str) -> None:
        self._ads_page.locator("textarea").first.fill(notes, timeout=self.READY_TIMEOUT_MS)

    def _fill_by_label_patterns(self, page: Any, labels: list[str], value: str, step_name: str) -> None:
        last_error: Exception | None = None
        for label in labels:
            try:
                field = page.get_by_label(re.compile(label, re.IGNORECASE)).first
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
        confirm = page.get_by_text(re.compile("Подтверд|Confirm", re.IGNORECASE)).last
        if confirm.count() > 0 and confirm.is_visible() and confirm.is_enabled():
            confirm.click(timeout=self.READY_TIMEOUT_MS)
            return
        if page.locator(".paymentItemNew").count() == 0:
            self._click_label_or_role(page, "способами оплаты", step_name="open-payment-methods")
        for name in wanted:
            item = page.locator(".paymentItemNew").filter(has_text=name).first
            item.click(timeout=self.READY_TIMEOUT_MS)
        confirm = page.get_by_text(re.compile("Подтверд|Confirm", re.IGNORECASE)).last
        if confirm.count() > 0 and confirm.is_visible() and confirm.is_enabled():
            confirm.click(timeout=self.READY_TIMEOUT_MS)

    def _dismiss_payment_modal_if_open(self, page: Any) -> None:
        has_payment_items = page.locator(".paymentItemNew").count() > 0
        has_payment_modal_text = page.get_by_text(
            re.compile("Управление способами оплаты|Manage Payment|Payment Method", re.IGNORECASE)
        ).count() > 0
        if not has_payment_items and not has_payment_modal_text:
            return

        confirm = page.get_by_text(re.compile("Подтверд|Confirm", re.IGNORECASE)).last
        if confirm.count() > 0 and confirm.is_visible() and confirm.is_enabled():
            confirm.click(timeout=self.READY_TIMEOUT_MS)
            page.wait_for_timeout(300)
            return

        cancel = page.get_by_text(re.compile("Отмена|Cancel", re.IGNORECASE)).last
        if cancel.count() > 0 and cancel.is_visible():
            cancel.click(timeout=self.READY_TIMEOUT_MS)
            page.wait_for_timeout(300)

    def _set_checkbox_by_text(self, page: Any, pattern: re.Pattern[str], checked: bool) -> None:
        checkbox = page.get_by_role("checkbox", name=pattern).first
        if checked:
            checkbox.check(timeout=self.READY_TIMEOUT_MS)
        else:
            checkbox.uncheck(timeout=self.READY_TIMEOUT_MS)

    def accept_terms(self, window_title: str) -> None:
        page = self._ads_page
        checkbox = page.get_by_role("checkbox", name=re.compile("прочитал|соглаша|agree", re.IGNORECASE)).or_(
            page.locator('input[type="checkbox"]')
        ).first
        try:
            checkbox.check(timeout=2_000)
        except Exception:
            page.locator("label").filter(has_text=re.compile("прочитал|соглаша|agree", re.IGNORECASE)).first.click(
                timeout=self.READY_TIMEOUT_MS
            )

    def submit_advertisement(self, window_title: str) -> None:
        self._click_label_or_role(self._ads_page, "Разместить объявления", step_name="submit-advertisement")

    def enter_security_password(self, window_title: str, password: str) -> None:
        page = self._ads_page
        self._fill_security_password_field(page, password)
        self._click_label_or_role(page, "Подтвердить", step_name="confirm-security-password")

    def _fill_security_password_field(self, page: Any, password: str) -> None:
        try:
            self._fill_by_label_patterns(page, [r"Финансовый пароль", r"Fund Password"], password, "security-password")
            return
        except Exception as label_error:
            last_error: Exception = label_error

        fields = page.locator('input[type="password"]')
        for index in range(fields.count()):
            field = fields.nth(index)
            try:
                if field.is_visible():
                    field.fill(password, timeout=self.READY_TIMEOUT_MS)
                    return
            except Exception as error:
                last_error = error
        self._save_failure_artifact(page, "security-password")
        raise RuntimeError(f"Не найдено видимое поле финансового пароля. Последняя ошибка: {last_error}")

    def _click_label_or_role(self, page: Any, text: str, *, step_name: str) -> None:
        pattern = re.compile(re.escape(text), re.IGNORECASE)
        target = page.get_by_role("button", name=pattern).or_(page.get_by_text(pattern)).first
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
