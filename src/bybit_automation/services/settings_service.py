from __future__ import annotations

import json
from pathlib import Path

from bybit_automation.models.app_state import AppState


class JsonSettingsService:
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path

    def save(self, state: AppState) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_path.write_text(
            json.dumps(state.to_dict(), indent=2),
            encoding="utf-8",
        )

    def load(self) -> AppState:
        if not self._file_path.exists():
            return AppState()
        payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        return AppState.from_dict(payload)
