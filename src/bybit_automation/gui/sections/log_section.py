from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QGroupBox, QMenu, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


class LogOutput(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.setMinimumHeight(self.fontMetrics().lineSpacing() * 11)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self._copy_shortcut.activated.connect(self.trigger_copy)

    def copy(self) -> None:
        self.trigger_copy()

    def trigger_copy(self) -> None:
        selected_text = self.textCursor().selectedText().replace("\u2029", "\n")
        if not selected_text:
            return
        QApplication.clipboard().setText(selected_text)

    def copy_all_text(self) -> None:
        full_text = self.toPlainText()
        if not full_text:
            return
        QApplication.clipboard().setText(full_text)

    def _show_context_menu(self, position) -> None:
        menu = QMenu(self)
        copy_action = QAction("Копировать", self)
        copy_action.triggered.connect(self.trigger_copy)
        copy_action.setEnabled(bool(self.textCursor().selectedText()))
        menu.addAction(copy_action)
        copy_all_action = QAction("Копировать весь лог", self)
        copy_all_action.triggered.connect(self.copy_all_text)
        copy_all_action.setEnabled(bool(self.toPlainText()))
        menu.addAction(copy_all_action)
        menu.exec(self.mapToGlobal(position))


class LogSection(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.log_output = LogOutput()
        self.copy_button = QPushButton("Копировать лог")
        self.clear_button = QPushButton("Очистить лог")
        self.copy_button.clicked.connect(self.log_output.copy_all_text)
        self.clear_button.clicked.connect(self.log_output.clear)

        group = QGroupBox("Лог")
        layout = QVBoxLayout(group)
        layout.addWidget(self.log_output)
        layout.addWidget(self.copy_button)
        layout.addWidget(self.clear_button)

        root_layout = QVBoxLayout(self)
        root_layout.addWidget(group)

    def append_message(self, message: str) -> None:
        self.log_output.appendPlainText(message)
