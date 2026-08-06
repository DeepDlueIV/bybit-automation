from __future__ import annotations

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
    def bridge_extension_dir(self) -> Path:
        bybiteye_dir = self.root_dir / "bybiteye extension"
        if bybiteye_dir.exists():
            for manifest_file in bybiteye_dir.rglob("manifest.json"):
                return manifest_file.parent
        return self.data_dir / "bridge-extension"

    @property
    def playwright_artifacts_dir(self) -> Path:
        return self.data_dir / "playwright-artifacts"

    @classmethod
    def from_cwd(cls) -> "AppPaths":
        root_dir = Path(__file__).resolve().parents[3]
        data_dir = root_dir / "data"
        settings_file = data_dir / "settings.json"
        found_accounts_file = data_dir / "found_accounts.txt"
        log_file = data_dir / "app.log"
        return cls(
            root_dir=root_dir,
            data_dir=data_dir,
            settings_file=settings_file,
            found_accounts_file=found_accounts_file,
            log_file=log_file,
        )
