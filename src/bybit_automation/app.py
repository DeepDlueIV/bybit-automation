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
    from bybit_automation.infrastructure.playwright_browser_driver import PlaywrightBrowserDriver
    from bybit_automation.infrastructure.portable_chrome_browser_driver import PortableChromeBrowserDriver
    from bybit_automation.infrastructure.windows_browser_finder import WindowsBrowserFinder
    from bybit_automation.models.automation_mode import AutomationMode
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
    playwright_profile_service = BybitExistingBrowserService(
        driver=PlaywrightBrowserDriver(
            logger=logger,
            mode=AutomationMode.PLAYWRIGHT_PROFILE,
            user_data_dir=app_paths.playwright_profile_dir,
            artifacts_dir=app_paths.playwright_artifacts_dir,
        ),
        logger=logger,
    )
    playwright_chromium_extensions_service = BybitExistingBrowserService(
        driver=PlaywrightBrowserDriver(
            logger=logger,
            mode=AutomationMode.PLAYWRIGHT_CHROMIUM_EXTENSIONS,
            user_data_dir=app_paths.playwright_chromium_extensions_profile_dir,
            artifacts_dir=app_paths.playwright_artifacts_dir,
            extension_dirs=[app_paths.bridge_extension_dir],
        ),
        logger=logger,
    )
    system_chrome_extensions_service = BybitExistingBrowserService(
        driver=PlaywrightBrowserDriver(
            logger=logger,
            mode=AutomationMode.SYSTEM_CHROME_EXTENSIONS_PROFILE,
            user_data_dir=app_paths.system_chrome_extensions_profile_dir,
            artifacts_dir=app_paths.playwright_artifacts_dir,
        ),
        logger=logger,
    )
    system_chrome_extensions_recovery_service = BybitExistingBrowserService(
        driver=PlaywrightBrowserDriver(
            logger=logger,
            mode=AutomationMode.SYSTEM_CHROME_EXTENSIONS_RECOVERY,
            user_data_dir=app_paths.system_chrome_extensions_profile_dir,
            artifacts_dir=app_paths.playwright_artifacts_dir,
        ),
        logger=logger,
    )
    portable_chrome_service = BybitExistingBrowserService(
        driver=PortableChromeBrowserDriver(
            logger=logger,
            chrome_executable=app_paths.portable_chrome_executable,
            user_data_dir=app_paths.portable_chrome_profile_dir,
            artifacts_dir=app_paths.playwright_artifacts_dir,
        ),
        logger=logger,
    )
    incogniton_cdp_service = BybitExistingBrowserService(
        driver=PlaywrightBrowserDriver(
            logger=logger,
            mode=AutomationMode.INCOGNITON_PLAYWRIGHT_CDP,
            user_data_dir=app_paths.playwright_profile_dir,
            artifacts_dir=app_paths.playwright_artifacts_dir,
        ),
        logger=logger,
    )
    browser_services = {
        AutomationMode.INCOGNITON_UIA: bybit_existing_browser_service,
        AutomationMode.PLAYWRIGHT_PROFILE: playwright_profile_service,
        AutomationMode.INCOGNITON_PLAYWRIGHT_CDP: incogniton_cdp_service,
        AutomationMode.PLAYWRIGHT_CHROMIUM_EXTENSIONS: playwright_chromium_extensions_service,
        AutomationMode.SYSTEM_CHROME_EXTENSIONS_PROFILE: system_chrome_extensions_service,
        AutomationMode.SYSTEM_CHROME_EXTENSIONS_RECOVERY: system_chrome_extensions_recovery_service,
        AutomationMode.PORTABLE_CHROME: portable_chrome_service,
    }
    position_sound_notifier = AccountFoundSoundNotifier(on_playback=lambda mode: logger.info("Звуковое уведомление: системный Windows." if mode == "system" else "Звуковое уведомление: fallback beep."))
    error_sound_notifier = ErrorSoundNotifier()
    merchant_cycle_service = MerchantCycleService(
        gateway=bybit_existing_browser_service,
        logger=logger,
        found_accounts_file=app_paths.found_accounts_file,
        position_sound_notifier=position_sound_notifier,
    )
    merchant_cycle_services = {
        mode: MerchantCycleService(
            gateway=service,
            logger=logger,
            found_accounts_file=app_paths.found_accounts_file,
            position_sound_notifier=position_sound_notifier,
        )
        for mode, service in browser_services.items()
    }
    controller = AppController(
        settings_service=settings_service,
        logger=logger,
        browser_discovery_service=browser_discovery_service,
        merchant_cycle_service=merchant_cycle_service,
        bybit_existing_browser_service=bybit_existing_browser_service,
        bybit_browser_services=browser_services,
        merchant_cycle_services=merchant_cycle_services,
        position_sound_notifier=position_sound_notifier,
        app_paths=app_paths,
    )
    return MainWindow(controller=controller, logger=logger, error_sound_notifier=error_sound_notifier)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = build_main_window()
    window.show()
    return app.exec()
