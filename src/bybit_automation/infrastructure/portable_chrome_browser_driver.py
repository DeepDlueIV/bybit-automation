from __future__ import annotations

import re
import subprocess
from pathlib import Path

from bybit_automation.infrastructure.playwright_browser_driver import PlaywrightBrowserDriver
from bybit_automation.models.automation_mode import AutomationMode
from bybit_automation.models.browser_discovery import BrowserDiscoveryResult
from bybit_automation.services.logging_service import AppLogger


PORTABLE_CHROME_VERSION = "150.0.7871.124"
PORTABLE_CHROME_BROWSER_NAME = "Portable Chrome 150"


class PortableChromeBrowserDriver(PlaywrightBrowserDriver):
    """Запускает закреплённый Chrome отдельным процессом и подключается к нему по CDP."""

    def __init__(
        self,
        logger: AppLogger,
        *,
        chrome_executable: Path,
        user_data_dir: Path,
        artifacts_dir: Path,
    ) -> None:
        self._portable_chrome_executable = chrome_executable
        super().__init__(
            logger=logger,
            mode=AutomationMode.PORTABLE_CHROME,
            user_data_dir=user_data_dir,
            artifacts_dir=artifacts_dir,
        )

    def _uses_system_chrome_extensions_profile(self) -> bool:
        return True

    def _find_chrome_executable(self) -> Path | None:
        if self._portable_chrome_executable.is_file():
            return self._portable_chrome_executable
        return None

    def open_profile(self, window_title: str) -> None:
        del window_title
        self._user_data_dir.mkdir(parents=True, exist_ok=True)
        chrome_executable = self._find_chrome_executable()
        if chrome_executable is None:
            raise RuntimeError(
                f"Portable Chrome {PORTABLE_CHROME_VERSION} не найден. "
                f"Ожидаемый файл: {self._portable_chrome_executable}. "
                "Открой запуск.txt в корне программы; для исходников в нём указана "
                "команда подготовки, для установленной версии требуется переустановка."
            )
        existing_port = self._find_existing_debug_port()
        if existing_port is not None:
            self._log(f"Portable Chrome 150 уже запущен на CDP-порту {existing_port}.")
            return
        port = self._find_free_port()
        command = self._build_extensions_chrome_command(
            chrome_executable=chrome_executable,
            remote_debugging_port=port,
        )
        self._log(f"открываю Portable Chrome {PORTABLE_CHROME_VERSION}: {command}")
        subprocess.Popen(command)

    def discover_profile(self) -> BrowserDiscoveryResult:
        result = super().discover_profile()
        return BrowserDiscoveryResult(
            browser_name=PORTABLE_CHROME_BROWSER_NAME,
            window_title=PORTABLE_CHROME_BROWSER_NAME if result.connected else "",
            tabs=result.tabs,
            ads_tab_title=result.ads_tab_title,
            sell_tab_title=result.sell_tab_title,
            connected=result.connected,
        )

    def select_trade_side(self, window_title: str, trade_side: str) -> None:
        del window_title
        page = self._ads_page
        self._dismiss_payment_modal_if_open(page)
        self._wait_for_bybit_interceptors_to_clear(page, "Ads form")
        button = page.locator("button").filter(
            has_text=re.compile(f"^{re.escape(trade_side)}$", re.IGNORECASE)
        ).first
        self._click_and_expect(
            page,
            lambda: button.click(timeout=self.READY_TIMEOUT_MS),
            lambda: button.wait_for(timeout=self.READY_TIMEOUT_MS),
            step_name="select-trade-side",
            expected=f"выбран тип объявления '{trade_side}'",
        )

    def close(self) -> None:
        # Portable Chrome принадлежит пользователю; закрываем только CDP-клиент приложения.
        self._drop_playwright_connection()
        self._chrome_process = None
