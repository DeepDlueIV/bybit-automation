from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QGroupBox

from bybit_automation.controllers.app_controller import AppController
from bybit_automation.gui.main_window import MainWindow
from bybit_automation.gui.sections.search_section import SearchSection
from bybit_automation.services.logging_service import AppLogger
from bybit_automation.services.settings_service import JsonSettingsService


def test_main_window_save_and_load_restore_form(qtbot, tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    window.advertisement_section.sell_button.setChecked(True)
    window.advertisement_section.fixed_price_edit.setText("123,45")
    window.advertisement_section.notes_edit.setPlainText("Saved note")
    window.advertisement_section.security_password_edit.setText("Secret1337$")
    window.search_section.depth_edit.setText("9")
    window.on_save_settings()

    window.advertisement_section.buy_button.setChecked(True)
    window.advertisement_section.fixed_price_edit.setText("1")
    window.advertisement_section.notes_edit.setPlainText("Changed")
    window.advertisement_section.security_password_edit.setText("Changed")
    window.search_section.depth_edit.setText("1")
    window.on_load_settings()

    assert window.advertisement_section.sell_button.isChecked() is True
    assert window.advertisement_section.fixed_price_edit.text() == "123,45"
    assert window.advertisement_section.notes_edit.toPlainText() == "Saved note"
    assert window.advertisement_section.security_password_edit.text() == "Secret1337$"
    assert window.search_section.depth_edit.text() == "9"


def test_main_window_has_expected_defaults(qtbot, tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    assert window.windowTitle() == "Автоматизация Bybit"
    assert window.statusBar().currentMessage() == "Готово"
    assert window.browser_section.connection_label.text() == "Не подключено"
    assert window.advertisement_section.buy_button.isChecked() is True
    assert window.advertisement_section.security_password_edit.text() == "Salam1337$"


def test_search_section_has_cycle_group_with_start_and_stop_buttons(qtbot) -> None:
    section = SearchSection()
    qtbot.addWidget(section)

    assert section.find_account_button.text() == "Найти свой акк"
    assert section.start_search_button.text() == "Старт"
    assert section.stop_search_button.text() == "Стоп"
    assert [group.title() for group in section.findChildren(QGroupBox)] == ["Поиск"]


def test_main_window_places_cycle_block_outside_search_group(qtbot, tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    group_titles = [group.title() for group in window.findChildren(QGroupBox)]

    assert "Поиск" in group_titles
    assert "Цикл" in group_titles


def test_main_window_find_my_account_button_triggers_controller(qtbot, tmp_path: Path) -> None:
    class FakeController(AppController):
        def __init__(self) -> None:
            super().__init__(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
            self.called = False

        def find_my_account(self, state) -> None:
            self.called = True

    controller = FakeController()
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    window.search_section.find_account_button.click()

    assert controller.called is True


def test_main_window_cycle_start_button_runs_cycle_worker(qtbot, tmp_path: Path) -> None:
    class FakeController(AppController):
        def __init__(self) -> None:
            super().__init__(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
            self.iterations = 0
            self.stop_callback = lambda: None

        def run_listing_cycle_iteration(self, state, *, stop_check=lambda: False) -> bool:
            self.iterations += 1
            self.stop_callback()
            return self.iterations == 1

    controller = FakeController()
    window = MainWindow(controller=controller, logger=controller._logger)
    controller.stop_callback = window.on_stop_cycle
    qtbot.addWidget(window)

    window.search_section.start_search_button.click()

    qtbot.waitUntil(lambda: controller.iterations >= 1, timeout=2000)
    qtbot.waitUntil(lambda: window._cycle_thread is None, timeout=2000)

    assert controller.iterations >= 1
    assert window.search_section.start_search_button.isEnabled() is True


def test_main_window_cycle_worker_can_run_three_iterations_without_silent_stop(qtbot, tmp_path: Path) -> None:
    class FakeController(AppController):
        def __init__(self) -> None:
            super().__init__(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
            self.iterations = 0
            self.worker = None

        def run_listing_cycle_iteration(self, state, *, stop_check=lambda: False) -> bool:
            self.iterations += 1
            if self.iterations >= 3 and self.worker is not None:
                self.worker.request_stop()
            return False

    controller = FakeController()
    window = MainWindow(controller=controller, logger=controller._logger)
    # Set worker reference after on_start_cycle creates it
    original_start = window.on_start_cycle

    def patched_start() -> None:
        original_start()
        controller.worker = window._cycle_worker

    window.on_start_cycle = patched_start  # type: ignore[method-assign]
    qtbot.addWidget(window)

    window.search_section.start_search_button.click()

    qtbot.waitUntil(lambda: controller.iterations >= 3, timeout=3000)
    qtbot.waitUntil(lambda: window._cycle_thread is None, timeout=3000)

    assert controller.iterations == 3
    assert window.search_section.start_search_button.isEnabled() is True


def test_main_window_cycle_logs_unexpected_exception_instead_of_silent_stop(qtbot, tmp_path: Path) -> None:
    class FakeController(AppController):
        def __init__(self) -> None:
            super().__init__(JsonSettingsService(tmp_path / "settings.json"), AppLogger())

        def run_listing_cycle_iteration(self, state, *, stop_check=lambda: False) -> bool:
            raise ValueError("unexpected boom")

    controller = FakeController()
    messages: list[str] = []
    controller._logger.subscribe(messages.append)
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    window.search_section.start_search_button.click()

    qtbot.waitUntil(lambda: window._cycle_thread is None, timeout=3000)

    assert any("unexpected boom" in message for message in messages)


def test_main_window_cycle_logs_exception_type_when_error_message_is_none(qtbot, tmp_path: Path) -> None:
    class FakeController(AppController):
        def __init__(self) -> None:
            super().__init__(JsonSettingsService(tmp_path / "settings.json"), AppLogger())

        def run_listing_cycle_iteration(self, state, *, stop_check=lambda: False) -> bool:
            raise RuntimeError(None)

    controller = FakeController()
    messages: list[str] = []
    controller._logger.subscribe(messages.append)
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    window.search_section.start_search_button.click()

    qtbot.waitUntil(lambda: window._cycle_thread is None, timeout=3000)

    assert any("RuntimeError(None)" in message for message in messages)


def test_main_window_cycle_stop_requests_worker_stop(qtbot, tmp_path: Path) -> None:
    found_file = tmp_path / "data" / "found_accounts.txt"
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    class FakeWorker:
        def __init__(self) -> None:
            self.stop_requested = False

        def request_stop(self) -> None:
            self.stop_requested = True

    worker = FakeWorker()
    window._cycle_worker = worker

    window.on_stop_cycle()

    assert worker.stop_requested is True


def test_main_window_fetch_current_price_updates_field(qtbot, tmp_path: Path) -> None:
    class FakeController(AppController):
        def fetch_current_price(self, state):
            updated_state = state.from_dict(state.to_dict())
            updated_state.advertisement.fixed_price = "80,99"
            return updated_state

    controller = FakeController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    window.browser_section.window_title_label.setText("Chrome - Bybit")
    window.advertisement_section.fixed_price_edit.setText("80")
    window.on_fetch_current_price()

    assert window.advertisement_section.fixed_price_edit.text() == "80,99"


def test_main_window_log_allows_text_selection(qtbot, tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    flags = window.log_section.log_output.textInteractionFlags()

    assert flags & Qt.TextSelectableByMouse
    assert flags & Qt.TextSelectableByKeyboard


def test_main_window_log_copy_puts_text_in_clipboard(monkeypatch, qtbot, tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    class FakeClipboard:
        def __init__(self) -> None:
            self.value = ""

        def setText(self, text: str) -> None:
            self.value = text

        def text(self) -> str:
            return self.value

    clipboard = FakeClipboard()
    monkeypatch.setattr("bybit_automation.gui.sections.log_section.QApplication.clipboard", lambda: clipboard)

    window.log_section.append_message("Первое сообщение")
    window.log_section.append_message("Второе сообщение")
    window.log_section.log_output.selectAll()
    window.log_section.log_output.copy()

    clipboard_text = QApplication.clipboard().text()

    assert "Первое сообщение" in clipboard_text
    assert "Второе сообщение" in clipboard_text


def test_main_window_log_ctrl_c_copies_selection(monkeypatch, qtbot, tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    class FakeClipboard:
        def __init__(self) -> None:
            self.value = ""

        def setText(self, text: str) -> None:
            self.value = text

        def text(self) -> str:
            return self.value

    clipboard = FakeClipboard()
    monkeypatch.setattr("bybit_automation.gui.sections.log_section.QApplication.clipboard", lambda: clipboard)

    window.log_section.append_message("Лог 1")
    window.log_section.append_message("Лог 2")
    window.log_section.log_output.selectAll()
    window.log_section.log_output.trigger_copy()

    assert "Лог 1" in clipboard.text()
    assert "Лог 2" in clipboard.text()


def test_main_window_log_copy_button_copies_selection(monkeypatch, qtbot, tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    class FakeClipboard:
        def __init__(self) -> None:
            self.value = ""

        def setText(self, text: str) -> None:
            self.value = text

        def text(self) -> str:
            return self.value

    clipboard = FakeClipboard()
    monkeypatch.setattr("bybit_automation.gui.sections.log_section.QApplication.clipboard", lambda: clipboard)

    window.log_section.append_message("copy me")
    window.log_section.log_output.selectAll()
    window.log_section.copy_button.click()

    assert "copy me" in clipboard.text()


def test_main_window_log_copy_button_copies_full_log_without_selection(monkeypatch, qtbot, tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    class FakeClipboard:
        def __init__(self) -> None:
            self.value = ""

        def setText(self, text: str) -> None:
            self.value = text

        def text(self) -> str:
            return self.value

    clipboard = FakeClipboard()
    monkeypatch.setattr("bybit_automation.gui.sections.log_section.QApplication.clipboard", lambda: clipboard)

    window.log_section.append_message("copy full 1")
    window.log_section.append_message("copy full 2")
    window.log_section.copy_button.click()

    assert "copy full 1" in clipboard.text()
    assert "copy full 2" in clipboard.text()


def test_main_window_log_clear_button_clears_widget_but_not_file_log(qtbot, tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger(log_file=log_file))
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    controller._logger.info("first line")
    controller._logger.info("second line")
    window.log_section.append_message("first line")
    window.log_section.append_message("second line")

    before_clear = log_file.read_text(encoding="utf-8")
    assert "first line" in before_clear
    assert "second line" in before_clear

    window.log_section.clear_button.click()

    assert window.log_section.log_output.toPlainText() == ""
    after_clear = log_file.read_text(encoding="utf-8")
    assert "first line" in after_clear
    assert "second line" in after_clear


def test_main_window_log_has_extra_height(qtbot, tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    line_height = window.log_section.log_output.fontMetrics().lineSpacing()

    assert window.log_section.log_output.minimumHeight() >= line_height * 11


def test_main_window_fill_form_logs_runtime_error(qtbot, tmp_path: Path) -> None:
    class FakeController(AppController):
        def fill_advertisement_form(self, state) -> bool:
            raise RuntimeError("Не найден popup 'Стандартная P2P-торговля'.")

    controller = FakeController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    messages: list[str] = []
    controller._logger.subscribe(messages.append)
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)

    window.on_fill_form()

    assert messages[-1] == "Не найден popup 'Стандартная P2P-торговля'."
    assert "Не удалось начать" in window.statusBar().currentMessage()


def test_main_window_updates_search_progress_and_result_labels(qtbot, tmp_path: Path) -> None:
    controller = AppController(JsonSettingsService(tmp_path / "settings.json"), AppLogger())
    window = MainWindow(controller=controller, logger=controller._logger)
    qtbot.addWidget(window)
    shown_messages: list[tuple[str, str]] = []
    MainWindow.QMessageBox_information = None

    window._on_search_progress(2, 5, "Ищу аккаунт")
    from bybit_automation.gui import main_window as main_window_module

    original_information = main_window_module.QMessageBox.information
    main_window_module.QMessageBox.information = lambda *args: shown_messages.append((args[1], args[2]))
    try:
        window._on_search_finished(True, "Аккаунт найден", "81,31", "ad-77", 2, 5, False)
    finally:
        main_window_module.QMessageBox.information = original_information

    assert window.search_section.current_page_label.text() == "2"
    assert window.search_section.current_position_label.text() == "5/10"
    assert window.search_section.search_status_label.text() == "Аккаунт найден"
    assert window.last_result_section.price_label.text() == "81,31"
    assert window.last_result_section.advertisement_id_label.text() == "ad-77"
    assert window.last_result_section.page_label.text() == "2"
    assert window.last_result_section.position_label.text() == "5/10"
    assert shown_messages == [("Поиск завершён", "Аккаунт найден")]
