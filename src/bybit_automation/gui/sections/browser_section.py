from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bybit_automation.models.automation_mode import AutomationMode
from bybit_automation.models.app_state import BrowserStatus


class BrowserSection(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["Incogniton", "System Chrome", "Playwright Chromium"])
        self.automation_mode_combo = QComboBox()
        self.automation_mode_combo.addItems(AutomationMode.choices())
        self.ads_tab_label = QLabel("Не подключено")
        self.sell_tab_label = QLabel("Не подключено")
        self.connection_label = QLabel("Не подключено")
        self.window_title_label = QLabel("")
        self.tabs_summary_label = QLabel("")
        self.tabs_summary_label.setWordWrap(True)
        self.check_browser_button = QPushButton("Проверить браузер")
        self.open_playwright_profile_button = QPushButton("Открыть Playwright-профиль")
        self.diagnose_sell_button = QPushButton("Диагностика Sell")
        self.diagnose_ads_button = QPushButton("Диагностика Ads")
        self.open_ads_form_button = QPushButton("Открыть форму Ads")
        self.check_browser_button.setMaximumWidth(180)
        self.open_playwright_profile_button.setMaximumWidth(240)
        self.diagnose_sell_button.setMaximumWidth(180)
        self.diagnose_ads_button.setMaximumWidth(180)
        self.open_ads_form_button.setMaximumWidth(180)

        self.window_title_label.setWordWrap(True)
        self.tabs_summary_label.setMaximumHeight(36)

        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.addWidget(self.check_browser_button)
        actions_layout.addWidget(self.open_playwright_profile_button)
        actions_layout.addWidget(self.diagnose_sell_button)
        actions_layout.addWidget(self.diagnose_ads_button)
        actions_layout.addWidget(self.open_ads_form_button)
        actions_layout.addStretch(1)

        self.browser_grid_layout = QGridLayout()
        self.browser_grid_layout.setHorizontalSpacing(12)
        self.browser_grid_layout.setVerticalSpacing(6)
        self.browser_grid_layout.addWidget(QLabel("Браузер"), 0, 0)
        self.browser_grid_layout.addWidget(self.browser_combo, 0, 1)
        self.browser_grid_layout.addWidget(QLabel("Автоматизация"), 0, 2)
        self.browser_grid_layout.addWidget(self.automation_mode_combo, 0, 3)
        self.browser_grid_layout.addWidget(QLabel("Подключение"), 1, 0)
        self.browser_grid_layout.addWidget(self.connection_label, 1, 1)
        self.browser_grid_layout.addWidget(QLabel("Ads"), 1, 2)
        self.browser_grid_layout.addWidget(self.ads_tab_label, 1, 3)
        self.browser_grid_layout.addWidget(QLabel("Sell"), 2, 0)
        self.browser_grid_layout.addWidget(self.sell_tab_label, 2, 1)
        self.browser_grid_layout.addWidget(QLabel("Окно"), 2, 2)
        self.browser_grid_layout.addWidget(self.window_title_label, 2, 3)
        self.browser_grid_layout.addLayout(actions_layout, 3, 0, 1, 2)
        self.browser_grid_layout.addWidget(QLabel("Вкладки"), 3, 2)
        self.browser_grid_layout.addWidget(self.tabs_summary_label, 3, 3)
        self.browser_grid_layout.setColumnStretch(1, 2)
        self.browser_grid_layout.setColumnStretch(3, 3)

        details = QFrame()
        details.setLayout(self.browser_grid_layout)

        group = QGroupBox("Браузер")
        group_layout = QVBoxLayout(group)
        group_layout.addWidget(details)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(group)

    def get_state(self) -> BrowserStatus:
        return BrowserStatus(
            browser_name=self.browser_combo.currentText(),
            automation_mode=self.automation_mode_combo.currentText(),
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
        mode_index = self.automation_mode_combo.findText(state.automation_mode)
        if mode_index >= 0:
            self.automation_mode_combo.setCurrentIndex(mode_index)
        self.ads_tab_label.setText(state.ads_tab_status)
        self.sell_tab_label.setText(state.sell_tab_status)
        self.connection_label.setText(state.connection_status)
        self.window_title_label.setText(state.window_title)
        self.tabs_summary_label.setText(state.tabs_summary)
