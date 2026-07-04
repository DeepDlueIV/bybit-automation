from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable


class AppLogger:
    def __init__(self, log_file: Path | None = None) -> None:
        self._callbacks: list[Callable[[str], None]] = []
        self._logger = logging.getLogger("bybit_automation")
        self._logger.setLevel(logging.INFO)
        self._log_file = log_file
        self._last_message_at: datetime | None = None
        if self._log_file is not None:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            session_started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"\n=== Новая сессия: {session_started} ===\n")

    def subscribe(self, callback: Callable[[str], None]) -> None:
        self._callbacks.append(callback)

    def info(self, message: str) -> None:
        now = datetime.now()
        delta_seconds = 0.0 if self._last_message_at is None else (now - self._last_message_at).total_seconds()
        self._last_message_at = now
        formatted = f"{now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} | +{delta_seconds:.3f}s | {message}"

        self._logger.info(formatted)
        if self._log_file is not None:
            with self._log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{formatted}\n")
        for callback in self._callbacks:
            callback(formatted)
