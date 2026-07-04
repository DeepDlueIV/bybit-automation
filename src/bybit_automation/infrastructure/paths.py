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

    @classmethod
    def from_cwd(cls) -> "AppPaths":
        root_dir = Path.cwd()
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
