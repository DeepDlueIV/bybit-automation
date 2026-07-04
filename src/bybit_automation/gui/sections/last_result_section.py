from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from bybit_automation.models.app_state import LastResult


class LastResultSection(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.price_label = QLabel("")
        self.advertisement_id_label = QLabel("")
        self.page_label = QLabel("")
        self.position_label = QLabel("")

        group = QGroupBox("Последний результат")
        form = QFormLayout()
        form.addRow("Цена", self.price_label)
        form.addRow("ID объявления", self.advertisement_id_label)
        form.addRow("Страница", self.page_label)
        form.addRow("Позиция", self.position_label)
        group.setLayout(form)

        layout = QVBoxLayout(self)
        layout.addWidget(group)

    def get_state(self) -> LastResult:
        return LastResult(
            price=self.price_label.text(),
            advertisement_id=self.advertisement_id_label.text(),
            page=self.page_label.text(),
            position=self.position_label.text(),
        )

    def set_state(self, state: LastResult) -> None:
        self.price_label.setText(state.price)
        self.advertisement_id_label.setText(state.advertisement_id)
        self.page_label.setText(state.page)
        self.position_label.setText(state.position)
