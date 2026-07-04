from __future__ import annotations

import subprocess
import sys


def test_app_module_import_does_not_break_qt_clipboard() -> None:
    script = """
from PySide6.QtWidgets import QApplication
from bybit_automation.app import build_main_window

app = QApplication.instance() or QApplication([])
clip = QApplication.clipboard()
clip.setText("before")
app.processEvents()
build_main_window()
clip.setText("after")
app.processEvents()
print(clip.text())
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "after"
