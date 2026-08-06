from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QIntValidator, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bybit_automation.models.app_state import AdvertisementSettings


class AdvertisementSection(QWidget):
    def __init__(self) -> None:
        super().__init__()

        price_validator = QRegularExpressionValidator(QRegularExpression(r"^\d+(,\d{0,2})?$"))
        integer_validator = QIntValidator(0, 999_999_999)

        self.buy_button = QPushButton("Покупка")
        self.sell_button = QPushButton("Продажа")
        self.buy_button.setCheckable(True)
        self.sell_button.setCheckable(True)
        self.buy_button.setChecked(True)

        self.trade_side_group = QButtonGroup(self)
        self.trade_side_group.setExclusive(True)
        self.trade_side_group.addButton(self.buy_button)
        self.trade_side_group.addButton(self.sell_button)

        self.fixed_price_edit = QLineEdit("80")
        self.fixed_price_edit.setValidator(price_validator)
        self.get_current_price_button = QPushButton("Подтянуть актуальную цену")

        self.payment_time_combo = QComboBox()
        self.payment_time_combo.addItems(["15 минут", "30 минут"])
        self.payment_time_combo.setCurrentText("30 минут")

        self.total_amount_edit = QLineEdit("20000")
        self.total_amount_edit.setValidator(integer_validator)
        self.minimum_transaction_edit = QLineEdit("4000")
        self.minimum_transaction_edit.setValidator(integer_validator)
        self.maximum_transaction_edit = QLineEdit("3500000")
        self.maximum_transaction_edit.setValidator(integer_validator)

        self.phone_linked_checkbox = QCheckBox("Номер телефона привязан")
        self.email_linked_checkbox = QCheckBox("Адрес электронной почты привязан")
        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(self.notes_edit.fontMetrics().lineSpacing() * 4 + 14)

        self.cash_deposit_checkbox = QCheckBox("Cash Deposit to Bank")
        self.mobile_top_up_checkbox = QCheckBox("Mobile Top-up")
        self.bank_transfer_checkbox = QCheckBox("Bank Transfer")

        self.security_password_edit = QLineEdit("Salam1337$")
        self.security_password_edit.setEchoMode(QLineEdit.EchoMode.Normal)

        self.save_settings_button = QPushButton("Сохранить настройки")
        self.load_settings_button = QPushButton("Загрузить настройки")
        self.reset_button = QPushButton("Сброс")
        self.fill_form_button = QPushButton("Удалить и добавить объявление")

        group = QGroupBox("Форма объявления")
        form = QFormLayout()

        trade_side_row = QHBoxLayout()
        trade_side_row.addWidget(self.buy_button)
        trade_side_row.addWidget(self.sell_button)
        trade_side_row.addStretch(1)
        form.addRow("Тип объявления", trade_side_row)

        form.addRow("Фиксированная цена (RUB за 1 USDT)", self.fixed_price_edit)
        form.addRow(self.get_current_price_button)
        form.addRow("Время оплаты", self.payment_time_combo)
        form.addRow("Общее количество (USDT)", self.total_amount_edit)
        form.addRow("Мин. сумма транзакции (RUB)", self.minimum_transaction_edit)
        form.addRow("Макс. сумма транзакции (RUB)", self.maximum_transaction_edit)

        requirements_row = QHBoxLayout()
        requirements_row.addWidget(self.phone_linked_checkbox)
        requirements_row.addWidget(self.email_linked_checkbox)
        form.addRow("Требования к контрагенту", requirements_row)

        form.addRow("Примечание", self.notes_edit)

        payment_methods = QHBoxLayout()
        payment_methods.addWidget(self.cash_deposit_checkbox)
        payment_methods.addWidget(self.mobile_top_up_checkbox)
        payment_methods.addWidget(self.bank_transfer_checkbox)
        form.addRow("Способы оплаты", payment_methods)
        form.addRow("Пароль проверки безопасности", self.security_password_edit)

        buttons = QGridLayout()
        buttons.addWidget(self.save_settings_button, 0, 0)
        buttons.addWidget(self.load_settings_button, 0, 1)
        buttons.addWidget(self.reset_button, 1, 0)
        buttons.addWidget(self.fill_form_button, 1, 1)

        wrapper = QVBoxLayout()
        wrapper.addLayout(form)
        wrapper.addLayout(buttons)
        group.setLayout(wrapper)

        layout = QVBoxLayout(self)
        layout.addWidget(group)

    def _current_trade_side(self) -> str:
        return "Покупка" if self.buy_button.isChecked() else "Продажа"

    def get_state(self) -> AdvertisementSettings:
        return AdvertisementSettings(
            trade_side=self._current_trade_side(),
            fixed_price=self.fixed_price_edit.text(),
            payment_time=self.payment_time_combo.currentText(),
            total_amount=self.total_amount_edit.text(),
            minimum_transaction=self.minimum_transaction_edit.text(),
            maximum_transaction=self.maximum_transaction_edit.text(),
            phone_linked=self.phone_linked_checkbox.isChecked(),
            email_linked=self.email_linked_checkbox.isChecked(),
            notes=self.notes_edit.toPlainText(),
            payment_cash_deposit=self.cash_deposit_checkbox.isChecked(),
            payment_mobile_top_up=self.mobile_top_up_checkbox.isChecked(),
            payment_bank_transfer=self.bank_transfer_checkbox.isChecked(),
            security_password=self.security_password_edit.text(),
        )

    def set_state(self, state: AdvertisementSettings) -> None:
        self.buy_button.setChecked(state.trade_side == "Покупка")
        self.sell_button.setChecked(state.trade_side == "Продажа")
        self.fixed_price_edit.setText(state.fixed_price)
        self.payment_time_combo.setCurrentText(state.payment_time)
        self.total_amount_edit.setText(state.total_amount)
        self.minimum_transaction_edit.setText(state.minimum_transaction)
        self.maximum_transaction_edit.setText(state.maximum_transaction)
        self.phone_linked_checkbox.setChecked(state.phone_linked)
        self.email_linked_checkbox.setChecked(state.email_linked)
        self.notes_edit.setPlainText(state.notes)
        self.cash_deposit_checkbox.setChecked(state.payment_cash_deposit)
        self.mobile_top_up_checkbox.setChecked(state.payment_mobile_top_up)
        self.bank_transfer_checkbox.setChecked(state.payment_bank_transfer)
        self.security_password_edit.setText(state.security_password)
