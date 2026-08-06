from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root_dir: Path
    data_dir: Path
    settings_file: Path
    found_accounts_file: Path
    log_file: Path

    @property
    def playwright_profile_dir(self) -> Path:
        return self.data_dir / "playwright-profile"

    @property
    def playwright_chromium_extensions_profile_dir(self) -> Path:
        return self.data_dir / "playwright-chromium-extensions-profile"

    @property
    def system_chrome_extensions_profile_dir(self) -> Path:
        return self.data_dir / "system-chrome-extensions-profile"

    @property
    def portable_chrome_profile_dir(self) -> Path:
        return self.data_dir / "portable-chrome-profile"

    @property
    def portable_chrome_executable(self) -> Path:
        return self.root_dir / "runtime" / "chrome-for-testing" / "chrome-win64" / "chrome.exe"

    @property
    def alarm_sound_file(self) -> Path:
        return self.root_dir / "sound" / "Alarm09.wav"

    @property
    def merchants_temp_file(self) -> Path:
        return self.data_dir / "merchants_temp.txt"

    @property
    def install_location_guide(self) -> Path:
        return self.root_dir / "ГДЕ_НАХОДЯТСЯ_ФАЙЛЫ.txt"

    @property
    def bridge_extension_dir(self) -> Path:
        bybiteye_dir = self.root_dir / "bybiteye extension"
        if bybiteye_dir.exists():
            for manifest_file in bybiteye_dir.rglob("manifest.json"):
                return manifest_file.parent
        return self.data_dir / "bridge-extension"

    @property
    def playwright_artifacts_dir(self) -> Path:
        return self.data_dir / "playwright-artifacts"

    def prepare_runtime_layout(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        guide = "\n".join(
            [
                "BYBIT AUTOMATION: РАСПОЛОЖЕНИЕ ФАЙЛОВ",
                "",
                f"Корень программы: {self.root_dir}",
                f"Настройки и рабочие данные: {self.data_dir}",
                f"Лог программы: {self.log_file}",
                f"Настройки: {self.settings_file}",
                f"Профиль Portable Chrome: {self.portable_chrome_profile_dir}",
                f"Portable Chrome: {self.portable_chrome_executable}",
                "",
                "Все изменяемые файлы программы находятся внутри указанного корня.",
            ]
        )
        self.install_location_guide.write_text(guide + "\n", encoding="utf-8")

    @classmethod
    def from_root(cls, root_dir: Path) -> "AppPaths":
        root_dir = root_dir.resolve()
        data_dir = root_dir / "data"
        return cls(
            root_dir=root_dir,
            data_dir=data_dir,
            settings_file=data_dir / "settings.json",
            found_accounts_file=data_dir / "found_accounts.txt",
            log_file=data_dir / "app.log",
        )

    @classmethod
    def from_runtime(
        cls,
        *,
        executable_path: Path | None = None,
        frozen: bool | None = None,
    ) -> "AppPaths":
        is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        if is_frozen:
            executable = executable_path or Path(sys.executable)
            return cls.from_root(executable.resolve().parent)
        override = os.environ.get("BYBIT_AUTOMATION_ROOT")
        if override:
            return cls.from_root(Path(override))
        return cls.from_root(Path(__file__).resolve().parents[3])

    @classmethod
    def from_cwd(cls) -> "AppPaths":
        return cls.from_runtime()
