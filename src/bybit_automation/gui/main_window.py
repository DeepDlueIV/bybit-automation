from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from bybit_automation.controllers.app_controller import AppController
from bybit_automation.gui.sections.advertisement_section import AdvertisementSection
from bybit_automation.gui.sections.browser_section import BrowserSection
from bybit_automation.gui.sections.log_section import LogSection
from bybit_automation.gui.sections.search_section import SearchSection
from bybit_automation.models.app_state import AppState
from bybit_automation.services.logging_service import AppLogger
from bybit_automation.services.sound_notifier import ErrorSoundNotifier


def _describe_exception(error: Exception) -> str:
    message = str(error).strip()
    if not message or message == "None":
        return repr(error)
    return message


def _running_under_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


class LogRelay(QObject):
    message = Signal(str)


class MerchantSearchWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(bool, str, str, str, int, int, bool)
    failed = Signal(str)

    def __init__(self, controller: AppController, state: AppState) -> None:
        super().__init__()
        self._controller = controller
        self._state = AppState.from_dict(state.to_dict())

    def run(self) -> None:
        try:
            result = self._controller.start_merchant_search(
                self._state,
                on_progress=lambda page, position, status: self.progress.emit(page, position, status),
            )
            if result is None:
                self.failed.emit("Сервис поиска Bybit не подключен.")
                return
            self.finished.emit(
                result.success,
                result.message,
                result.price,
                result.advertisement_id,
                result.page,
                result.position,
                result.stopped,
            )
        except Exception as error:
            self.failed.emit(_describe_exception(error))


class ListingCycleWorker(QObject):
    progress = Signal(str)
    found_position = Signal(int)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, controller: AppController, state: AppState) -> None:
        super().__init__()
        self._controller = controller
        self._state = AppState.from_dict(state.to_dict())
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        iteration = 0
        try:
            while not self._stop_requested:
                iteration += 1
                self.progress.emit(f"Цикл: итерация {iteration} началась.")
                found = self._controller.run_listing_cycle_iteration(
                    self._state, stop_check=lambda: self._stop_requested
                )
                if found:
                    position = getattr(self._controller, "last_found_position", 0)
                    if position:
                        self.found_position.emit(position)
                    self.progress.emit("Цикл: аккаунт найден, результат записан. Начинаю новую итерацию.")
                else:
                    self.progress.emit("Цикл: аккаунт не найден. Начинаю новую итерацию.")
            self.finished.emit("Цикл остановлен.")
        except Exception as error:
            self.failed.emit(_describe_exception(error))


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController, logger: AppLogger, error_sound_notifier: ErrorSoundNotifier | None = None) -> None:
        super().__init__()
        self._controller = controller
        self._logger = logger
        self._error_sound_notifier = error_sound_notifier or ErrorSoundNotifier()
        self._search_thread: QThread | None = None
        self._search_worker: MerchantSearchWorker | None = None
        self._cycle_thread: QThread | None = None
        self._cycle_worker: ListingCycleWorker | None = None
        self._log_relay = LogRelay()

        self.setWindowTitle("Автоматизация Bybit")
        self.resize(1280, 920)

        self.browser_section = BrowserSection()
        self.advertisement_section = AdvertisementSection()
        self.search_section = SearchSection()
        self.log_section = LogSection()

        self._build_layout()
        self._build_menu()
        self._connect_signals()
        self._log_relay.message.connect(self.log_section.append_message)
        self._logger.subscribe(self._log_relay.message.emit)

        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Готово")
        self.setStatusBar(self.status_bar)
        self.apply_state(self._controller.default_state())
        self._set_search_running(False)
        self._logger.info("Приложение запущено.")

    def _build_layout(self) -> None:
        content = QWidget()
        main_layout = QVBoxLayout(content)

        top_row = QHBoxLayout()
        top_row.addWidget(self.browser_section, 1)

        main_layout.addLayout(top_row)
        main_layout.addWidget(self.advertisement_section)
        main_layout.addWidget(self.search_section)
        main_layout.addWidget(self.search_section.cycle_group)
        main_layout.addWidget(self.log_section)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(content)
        self.setCentralWidget(scroll_area)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Файл")
        help_menu = self.menuBar().addMenu("Помощь")

        self.load_action = QAction("Загрузить настройки", self)
        self.save_action = QAction("Сохранить настройки", self)
        self.exit_action = QAction("Выход", self)
        self.about_action = QAction("О программе", self)

        file_menu.addAction(self.load_action)
        file_menu.addAction(self.save_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        help_menu.addAction(self.about_action)

    def _connect_signals(self) -> None:
        self.advertisement_section.save_settings_button.clicked.connect(self.on_save_settings)
        self.advertisement_section.load_settings_button.clicked.connect(self.on_load_settings)
        self.advertisement_section.reset_button.clicked.connect(self.on_reset_settings)
        self.advertisement_section.fill_form_button.clicked.connect(self.on_fill_form)
        self.advertisement_section.get_current_price_button.clicked.connect(self.on_fetch_current_price)
        self.browser_section.check_browser_button.clicked.connect(self.on_discover_browser)
        self.browser_section.open_playwright_profile_button.clicked.connect(self.on_open_playwright_profile)
        self.browser_section.diagnose_sell_button.clicked.connect(self.on_diagnose_sell_page)
        self.browser_section.diagnose_ads_button.clicked.connect(self.on_diagnose_ads_page)
        self.browser_section.open_ads_form_button.clicked.connect(self.on_open_ads_form)
        self.search_section.collect_merchants_button.clicked.connect(self.on_collect_merchants)
        self.search_section.find_account_button.clicked.connect(self.on_start_search)
        self.search_section.start_search_button.clicked.connect(self.on_start_cycle)
        self.search_section.stop_search_button.clicked.connect(self.on_stop_cycle)
        self.search_section.save_result_button.clicked.connect(self.on_save_result)
        self.save_action.triggered.connect(self.on_save_settings)
        self.load_action.triggered.connect(self.on_load_settings)
        self.exit_action.triggered.connect(self.close)
        self.about_action.triggered.connect(self.on_about)

    def collect_state(self) -> AppState:
        return AppState(
            browser=self.browser_section.get_state(),
            advertisement=self.advertisement_section.get_state(),
            search=self.search_section.get_state(),
        )

    def apply_state(self, state: AppState) -> None:
        self.browser_section.set_state(state.browser)
        self.advertisement_section.set_state(state.advertisement)
        self.search_section.set_state(state.search)

    def _set_search_running(self, running: bool) -> None:
        self.search_section.start_search_button.setEnabled(not running)
        self.search_section.stop_search_button.setEnabled(running)

    def _cleanup_search_thread(self) -> None:
        if self._search_thread is None:
            return
        self._search_thread.quit()
        self._search_thread.wait()
        self._search_thread = None
        self._search_worker = None
        self._set_search_running(False)

    def _cleanup_cycle_thread(self) -> None:
        if self._cycle_thread is None:
            return
        self._cycle_thread.quit()
        self._cycle_thread.wait()
        self._cycle_thread = None
        self._cycle_worker = None
        self._set_search_running(False)

    def on_save_settings(self) -> None:
        self._controller.save_settings(self.collect_state())
        self.status_bar.showMessage("Настройки сохранены")

    def on_load_settings(self) -> None:
        self.apply_state(self._controller.load_settings())
        self.status_bar.showMessage("Настройки загружены")

    def on_reset_settings(self) -> None:
        self.apply_state(self._controller.reset_settings())
        self.status_bar.showMessage("Настройки сброшены")

    def on_placeholder(self, action_name: str) -> None:
        self._controller.placeholder_action(action_name)
        self.status_bar.showMessage(f"{action_name} пока не реализовано")

    def on_discover_browser(self) -> None:
        current_state = self.collect_state()
        discovered_state = self._controller.discover_browser(self.browser_section.browser_combo.currentText())
        current_state.browser = discovered_state.browser
        current_state.browser.automation_mode = self.browser_section.automation_mode_combo.currentText()
        self.apply_state(current_state)
        self.status_bar.showMessage("Браузер проверен")

    def on_open_playwright_profile(self) -> None:
        try:
            opened = self._controller.open_selected_browser_profile(self.collect_state())
        except (RuntimeError, KeyError) as error:
            self._logger.info(_describe_exception(error))
            self.status_bar.showMessage("Не удалось открыть Playwright-профиль")
            return
        if opened:
            self.status_bar.showMessage("Playwright-профиль открыт")
        else:
            self.status_bar.showMessage("Выбранный режим не поддерживает открытие профиля")

    def on_fill_form(self) -> None:
        try:
            started = self._controller.fill_advertisement_form(self.collect_state())
        except (RuntimeError, KeyError) as error:
            self._logger.info(_describe_exception(error))
            self.status_bar.showMessage("Не удалось начать заполнение формы")
            return
        if started:
            self.status_bar.showMessage("Заполнение формы запущено")
        else:
            self.status_bar.showMessage("Не удалось начать заполнение формы")

    def on_fetch_current_price(self) -> None:
        try:
            state = self._controller.fetch_current_price(self.collect_state())
        except (RuntimeError, KeyError) as error:
            self._logger.info(_describe_exception(error))
            self.status_bar.showMessage("Не удалось подтянуть цену")
            return
        self.apply_state(state)
        self.status_bar.showMessage("Актуальная цена подтянута")

    def on_diagnose_sell_page(self) -> None:
        try:
            path = self._controller.diagnose_sell_page(self.collect_state())
        except (RuntimeError, KeyError) as error:
            self._logger.info(_describe_exception(error))
            self.status_bar.showMessage("Не удалось выполнить Sell-диагностику")
            return
        if path is None:
            self.status_bar.showMessage("Sell-диагностика недоступна")
            return
        self.status_bar.showMessage(f"Sell-диагностика сохранена: {path}")

    def on_diagnose_ads_page(self) -> None:
        try:
            path = self._controller.diagnose_ads_page(self.collect_state())
        except (RuntimeError, KeyError) as error:
            self._logger.info(_describe_exception(error))
            self.status_bar.showMessage("Не удалось выполнить Ads-диагностику")
            return
        if path is None:
            self.status_bar.showMessage("Ads-диагностика недоступна")
            return
        self.status_bar.showMessage(f"Ads-диагностика сохранена: {path}")

    def on_open_ads_form(self) -> None:
        try:
            opened = self._controller.open_ads_form_for_smoke_check(self.collect_state())
        except (RuntimeError, KeyError) as error:
            self._logger.info(_describe_exception(error))
            self.status_bar.showMessage("Не удалось открыть форму Ads")
            return
        if opened:
            self.status_bar.showMessage("Форма Ads открыта для безопасной проверки")
        else:
            self.status_bar.showMessage("Открытие формы Ads недоступно для выбранного режима")

    def on_start_search(self) -> None:
        state = self.collect_state()
        self._controller.find_my_account(state)
        position = getattr(self._controller, "last_found_position", 0)
        if position:
            self.search_section.set_last_found_position(position)

    def on_start_cycle(self) -> None:
        if self._cycle_thread is not None:
            return
        self._cycle_worker = ListingCycleWorker(self._controller, self.collect_state())
        self._cycle_thread = QThread(self)
        self._cycle_worker.moveToThread(self._cycle_thread)
        self._cycle_thread.started.connect(self._cycle_worker.run)
        self._cycle_worker.progress.connect(self._on_cycle_progress)
        self._cycle_worker.found_position.connect(self.search_section.set_last_found_position)
        self._cycle_worker.finished.connect(self._on_cycle_finished)
        self._cycle_worker.failed.connect(self._on_cycle_failed)
        self._cycle_worker.finished.connect(self._cleanup_cycle_thread)
        self._cycle_worker.failed.connect(self._cleanup_cycle_thread)
        self._set_search_running(True)
        self.status_bar.showMessage("Цикл запущен")
        self._cycle_thread.start()

    def on_stop_cycle(self) -> None:
        if self._cycle_worker is not None:
            self._cycle_worker.request_stop()

    def on_stop_search(self) -> None:
        self._controller.stop_merchant_search()
        self.search_section.search_status_label.setText("Останавливаю поиск")
        self.status_bar.showMessage("Останавливаю поиск")

    def on_collect_merchants(self) -> None:
        state = self.collect_state()
        try:
            merchants = self._controller.collect_all_merchants(state)
        except (RuntimeError, KeyError) as error:
            self._logger.info(_describe_exception(error))
            self.status_bar.showMessage("Не удалось собрать мерчантов")
            return

        if not merchants:
            self._logger.info("Мерчанты не найдены")
            self.status_bar.showMessage("Мерчанты не найдены")
            return

        temp_path = Path.cwd() / "data" / "merchants_temp.txt"
        temp_path.write_text("\n".join(merchants) + "\n", encoding="utf-8")

        self._logger.info(f"Собрано мерчантов: {len(merchants)}. Сохранено: {temp_path}")
        self.status_bar.showMessage(f"Собрано {len(merchants)} мерчантов")

    def on_save_result(self) -> None:
        self.on_placeholder("Записать результат")

    def _on_search_progress(self, page: int, position: int, status: str) -> None:
        self.search_section.current_page_label.setText(str(page) if page else "")
        self.search_section.current_position_label.setText(f"{position}/10" if position else "")
        self.search_section.search_status_label.setText(status)
        page_text = f"страница {page}" if page else "страница не определена"
        position_text = f", позиция {position}/10" if position else ""
        self._logger.info(f"Поиск: {page_text}{position_text}: {status}")

    def _on_cycle_progress(self, status: str) -> None:
        self.search_section.search_status_label.setText(status)
        self._logger.info(status)

    def _on_cycle_finished(self, message: str) -> None:
        self.search_section.search_status_label.setText(message)
        self.status_bar.showMessage(message)

    def _on_cycle_failed(self, message: str) -> None:
        self.search_section.search_status_label.setText(message)
        self._logger.info(message)
        self.status_bar.showMessage("Цикл завершился с ошибкой")
        if _running_under_pytest():
            return
        self._error_sound_notifier.play()
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Ошибка цикла")
        msg.setText(f"Цикл завершился с ошибкой:\n{message}")
        msg.setStandardButtons(QMessageBox.Ok)
        QTimer.singleShot(0, msg.show)

    def _on_search_finished(
        self,
        success: bool,
        message: str,
        price: str,
        advertisement_id: str,
        page: int,
        position: int,
        stopped: bool,
    ) -> None:
        self.search_section.search_status_label.setText(message)
        if page:
            self.search_section.current_page_label.setText(str(page))
        if position:
            self.search_section.current_position_label.setText(f"{position}/10")
        if success:
            self.search_section.set_last_found_position(position)
            QMessageBox.information(self, "Поиск завершён", "Аккаунт найден")
            self.status_bar.showMessage("Аккаунт найден")
        elif stopped:
            self.status_bar.showMessage("Поиск остановлен")
        else:
            self.status_bar.showMessage(message)

    def _on_search_failed(self, message: str) -> None:
        self.search_section.search_status_label.setText(message)
        self._logger.info(message)
        self.status_bar.showMessage("Поиск завершился с ошибкой")

    def on_about(self) -> None:
        QMessageBox.about(
            self,
            "О программе",
            "Автоматизация Bybit\n\nКаркас Phase 1 на PySide6.",
        )
