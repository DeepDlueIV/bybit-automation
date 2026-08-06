from __future__ import annotations

from pathlib import Path

from bybit_automation.infrastructure.paths import AppPaths
from bybit_automation.infrastructure.portable_chrome_browser_driver import (
    PORTABLE_CHROME_VERSION,
)


def test_frozen_runtime_uses_executable_directory_as_single_root(tmp_path: Path) -> None:
    executable = tmp_path / "installed" / "BybitAutomation.exe"

    paths = AppPaths.from_runtime(executable_path=executable, frozen=True)

    assert paths.root_dir == executable.parent
    assert paths.data_dir == executable.parent / "data"
    assert paths.log_file == executable.parent / "data" / "app.log"
    assert paths.portable_chrome_executable == (
        executable.parent / "runtime" / "chrome-for-testing" / "chrome-win64" / "chrome.exe"
    )
    assert paths.alarm_sound_file == executable.parent / "sound" / "Alarm09.wav"


def test_frozen_runtime_ignores_source_root_override(tmp_path: Path, monkeypatch) -> None:
    executable = tmp_path / "installed" / "BybitAutomation.exe"
    monkeypatch.setenv("BYBIT_AUTOMATION_ROOT", str(tmp_path / "wrong-root"))

    paths = AppPaths.from_runtime(executable_path=executable, frozen=True)

    assert paths.root_dir == executable.parent


def test_runtime_layout_creates_data_and_location_guide(tmp_path: Path) -> None:
    paths = AppPaths.from_root(tmp_path / "BybitAutomation")

    paths.prepare_runtime_layout()

    assert paths.data_dir.is_dir()
    guide = paths.install_location_guide.read_text(encoding="utf-8")
    assert str(paths.root_dir) in guide
    assert str(paths.log_file) in guide
    assert str(paths.settings_file) in guide
    assert str(paths.portable_chrome_profile_dir) in guide


def test_preflight_reports_missing_portable_chrome_with_actionable_paths(tmp_path: Path) -> None:
    from bybit_automation.diagnostics.runtime_preflight import run_runtime_preflight

    paths = AppPaths.from_root(tmp_path / "BybitAutomation")

    report = run_runtime_preflight(paths)

    assert report.ok is False
    browser_check = report.check("portable_chrome")
    assert browser_check.ok is False
    assert str(paths.portable_chrome_executable) in browser_check.message
    assert PORTABLE_CHROME_VERSION in browser_check.message
    assert str(paths.log_file) in report.summary


def test_preflight_accepts_complete_runtime_layout(tmp_path: Path) -> None:
    from bybit_automation.diagnostics.runtime_preflight import run_runtime_preflight

    paths = AppPaths.from_root(tmp_path / "BybitAutomation")
    paths.portable_chrome_executable.parent.mkdir(parents=True)
    paths.portable_chrome_executable.touch()
    paths.alarm_sound_file.parent.mkdir(parents=True)
    paths.alarm_sound_file.touch()

    report = run_runtime_preflight(paths)

    assert report.ok is True
    assert report.check("runtime_root").ok is True
    assert report.check("data_directory").ok is True
    assert report.check("portable_chrome").ok is True
    assert report.check("alarm_sound").ok is True
