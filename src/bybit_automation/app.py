from __future__ import annotations

import ctypes
import sys

from PySide6.QtWidgets import QApplication


def _ensure_sta_com() -> None:
    ctypes.windll.ole32.OleInitialize(None)


_ensure_sta_com()

from bybit_automation.controllers.app_controller import AppController
from bybit_automation.gui.main_window import MainWindow
from bybit_automation.infrastructure.paths import AppPaths
from bybit_automation.services.logging_service import AppLogger
from bybit_automation.services.settings_service import JsonSettingsService


def build_main_window() -> MainWindow:
    from bybit_automation.infrastructure.existing_browser_window_driver import ExistingBrowserWindowDriver
    from bybit_automation.infrastructure.windows_browser_finder import WindowsBrowserFinder
    from bybit_automation.services.browser_discovery_service import BrowserDiscoveryService
    from bybit_automation.services.bybit_existing_browser_service import BybitExistingBrowserService
    from bybit_automation.services.merchant_cycle_service import MerchantCycleService
    from bybit_automation.services.sound_notifier import ErrorSoundNotifier, AccountFoundSoundNotifier

    app_paths = AppPaths.from_cwd()
    logger = AppLogger(log_file=app_paths.log_file)
    settings_service = JsonSettingsService(app_paths.settings_file)
    browser_discovery_service = BrowserDiscoveryService(finder=WindowsBrowserFinder())
    bybit_existing_browser_service = BybitExistingBrowserService(
        driver=ExistingBrowserWindowDriver(logger=logger),
        logger=logger,
    )
    position_sound_notifier = AccountFoundSoundNotifier(on_playback=lambda mode: logger.info("Звуковое уведомление: системный Windows." if mode == "system" else "Звуковое уведомление: fallback beep."))
    error_sound_notifier = ErrorSoundNotifier()
    merchant_cycle_service = MerchantCycleService(
        gateway=bybit_existing_browser_service,
        logger=logger,
        found_accounts_file=app_paths.found_accounts_file,
        position_sound_notifier=position_sound_notifier,
    )
    controller = AppController(
        settings_service=settings_service,
        logger=logger,
        browser_discovery_service=browser_discovery_service,
        merchant_cycle_service=merchant_cycle_service,
        bybit_existing_browser_service=bybit_existing_browser_service,
        position_sound_notifier=position_sound_notifier,
        app_paths=app_paths,
    )
    return MainWindow(controller=controller, logger=logger, error_sound_notifier=error_sound_notifier)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = build_main_window()
    window.show()
    return app.exec()
