from __future__ import annotations

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bybit_automation.models.app_state import SearchSettings


def _position_range_label(position: int) -> str:
    if position < 1:
        return ""
    return str(position)


class SearchSection(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.account_name_edit = QLineEdit()
        self.depth_edit = QLineEdit("4")
        self.depth_edit.setValidator(QIntValidator(1, 999))

        self.collect_merchants_button = QPushButton("Собрать мерчантов")
        self.find_account_button = QPushButton("Найти свой акк")
        self.start_search_button = QPushButton("Старт")
        self.stop_search_button = QPushButton("Стоп")
        self.stop_search_button.setMaximumWidth(120)
        self.save_result_button = QPushButton("Записать результат")

        self.current_page_label = QLabel("")
        self.current_position_label = QLabel("")
        self.search_status_label = QLabel("")
        self.last_found_position_label = QLabel("Последняя найдена позиция: не найдено")

        group = QGroupBox("Поиск")
        form = QFormLayout()

        buttons_row = QWidget()
        buttons_layout = QHBoxLayout(buttons_row)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.addWidget(self.start_search_button)
        buttons_layout.addWidget(self.stop_search_button)

        cycle_group = QGroupBox("Цикл")
        cycle_layout = QVBoxLayout()
        cycle_layout.addWidget(buttons_row)
        cycle_layout.addWidget(self.last_found_position_label)
        cycle_group.setLayout(cycle_layout)
        self.cycle_group = cycle_group

        form.addRow("Имя аккаунта", self.account_name_edit)
        form.addRow("Глубина", self.depth_edit)
        form.addRow(self.collect_merchants_button)
        form.addRow(self.find_account_button)
        form.addRow(self.save_result_button)
        form.addRow("Текущая страница", self.current_page_label)
        form.addRow("Текущая позиция", self.current_position_label)
        form.addRow("Статус поиска", self.search_status_label)
        group.setLayout(form)

        layout = QVBoxLayout(self)
        layout.addWidget(group)

    def set_last_found_position(self, position: int) -> None:
        range_text = _position_range_label(position)
        value = range_text or "не найдено"
        self.last_found_position_label.setText(f"Последняя найдена позиция: {value}")

    def get_state(self) -> SearchSettings:
        return SearchSettings(
            account_name=self.account_name_edit.text(),
            depth=self.depth_edit.text(),
            current_page=self.current_page_label.text(),
            current_position=self.current_position_label.text(),
            search_status=self.search_status_label.text(),
        )

    def set_state(self, state: SearchSettings) -> None:
        self.account_name_edit.setText(state.account_name)
        self.depth_edit.setText(state.depth)
        self.current_page_label.setText(state.current_page)
        self.current_position_label.setText(state.current_position)
        self.search_status_label.setText(state.search_status)
