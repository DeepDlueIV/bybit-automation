from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from bybit_automation.models.app_state import BrowserStatus


class BrowserSection(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["Incogniton", "Chrome", "Edge", "Brave", "Chromium", "Firefox"])
        self.ads_tab_label = QLabel("Не подключено")
        self.sell_tab_label = QLabel("Не подключено")
        self.connection_label = QLabel("Не подключено")
        self.window_title_label = QLabel("")
        self.tabs_summary_label = QLabel("")
        self.tabs_summary_label.setWordWrap(True)
        self.check_browser_button = QPushButton("Проверить браузер")

        details = QWidget()
        form = QFormLayout(details)
        form.addRow("Выбор браузера", self.browser_combo)
        form.addRow("Вкладка Ads", self.ads_tab_label)
        form.addRow("Вкладка Sell", self.sell_tab_label)
        form.addRow("Подключение", self.connection_label)
        form.addRow("Окно браузера", self.window_title_label)
        form.addRow("Вкладки", self.tabs_summary_label)
        form.addRow(self.check_browser_button)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setWidget(details)

        group = QGroupBox("Браузер")
        group_layout = QVBoxLayout(group)
        group_layout.addWidget(scroll_area)

        layout = QVBoxLayout(self)
        layout.addWidget(group)

    def get_state(self) -> BrowserStatus:
        return BrowserStatus(
            browser_name=self.browser_combo.currentText(),
            ads_tab_status=self.ads_tab_label.text(),
            sell_tab_status=self.sell_tab_label.text(),
            connection_status=self.connection_label.text(),
            window_title=self.window_title_label.text(),
            tabs_summary=self.tabs_summary_label.text(),
        )

    def set_state(self, state: BrowserStatus) -> None:
        index = self.browser_combo.findText(state.browser_name)
        if index >= 0:
            self.browser_combo.setCurrentIndex(index)
        self.ads_tab_label.setText(state.ads_tab_status)
        self.sell_tab_label.setText(state.sell_tab_status)
        self.connection_label.setText(state.connection_status)
        self.window_title_label.setText(state.window_title)
        self.tabs_summary_label.setText(state.tabs_summary)
