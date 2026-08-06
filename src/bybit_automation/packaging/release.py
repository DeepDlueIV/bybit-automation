from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any
import winreg


PYINSTALLER_VERSION = "6.21.0"
INNO_SETUP_VERSION = "6.7.3"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_release_inputs(
    root_dir: Path,
    *,
    chrome_executable: Path | None = None,
) -> None:
    chrome_executable = chrome_executable or (
        root_dir / "runtime" / "chrome-for-testing" / "chrome-win64" / "chrome.exe"
    )
    required = (
        ("Portable Chrome", chrome_executable),
        ("звуковой файл", root_dir / "sound" / "Alarm09.wav"),
        ("общая инструкция", root_dir / "запуск.txt"),
        ("PyInstaller spec", root_dir / "packaging" / "BybitAutomation.spec"),
        ("Inno Setup script", root_dir / "packaging" / "BybitAutomation.iss"),
    )
    for label, path in required:
        if not path.is_file():
            raise RuntimeError(f"Не найден {label}: {path}")


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "name": path.name,
        "size": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _directory_record(path: Path) -> dict[str, Any]:
    files = sorted(
        (candidate for candidate in path.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(path).as_posix(),
    )
    digest = hashlib.sha256()
    total_size = 0
    for file_path in files:
        relative_path = file_path.relative_to(path).as_posix()
        size = file_path.stat().st_size
        total_size += size
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_sha256(file_path).encode("ascii"))
        digest.update(b"\0")
    return {
        "name": path.name,
        "file_count": len(files),
        "size": total_size,
        "sha256": digest.hexdigest(),
    }


def create_release_manifest(
    *,
    app_version: str,
    python_version: str,
    pyinstaller_version: str,
    inno_setup_version: str,
    playwright_version: str,
    chrome_version: str,
    app_executable: Path,
    chrome_executable: Path,
    installer: Path | None = None,
) -> dict[str, Any]:
    files = {
        "application": _file_record(app_executable),
        "application_runtime": _directory_record(app_executable.parent / "_internal"),
        "portable_chrome": _file_record(chrome_executable),
        "portable_chrome_runtime": _directory_record(chrome_executable.parent),
    }
    if installer is not None:
        files["installer"] = _file_record(installer)
    return {
        "product": "Bybit Automation",
        "versions": {
            "application": app_version,
            "python": python_version,
            "pyinstaller": pyinstaller_version,
            "inno_setup": inno_setup_version,
            "playwright": playwright_version,
            "portable_chrome": chrome_version,
        },
        "files": files,
    }


def write_release_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def find_inno_setup_compiler() -> Path:
    configured = os.environ.get("INNO_SETUP_COMPILER")
    candidates = [
        Path(configured) if configured else None,
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise RuntimeError(
        "Inno Setup 6.7.3 не найден. Установи его командой из "
        "docs/build-windows-installer.md или задай INNO_SETUP_COMPILER."
    )


def read_inno_setup_version(compiler: Path) -> str:
    uninstall_keys = (
        r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
    )
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for key_name in uninstall_keys:
            try:
                with winreg.OpenKey(root, key_name) as key:
                    install_location = Path(str(winreg.QueryValueEx(key, "InstallLocation")[0]))
                    version = str(winreg.QueryValueEx(key, "DisplayVersion")[0])
            except FileNotFoundError:
                continue
            if compiler.resolve().is_relative_to(install_location.resolve()):
                return version
    raise RuntimeError(
        f"Не удалось определить версию Inno Setup для {compiler}. "
        "Установи закреплённую версию из docs/build-windows-installer.md."
    )


def require_tool_version(label: str, *, actual: str, expected: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label}: ожидалась {expected}, обнаружена {actual}")


def require_windows_x64_build(*, machine: str, pointer_bits: int) -> None:
    if machine.casefold() not in {"amd64", "x86_64"} or pointer_bits != 64:
        raise RuntimeError(
            f"Релиз нужно собирать в Windows x64 Python; обнаружено {machine}, {pointer_bits}-bit"
        )


def validate_release_instruction_versions(root_dir: Path, *, app_version: str) -> None:
    expected_name = f"BybitAutomation-Setup-{app_version}.exe"
    instruction_paths = (
        root_dir / "запуск.txt",
        root_dir / "docs" / "build-windows-installer.md",
    )
    for path in instruction_paths:
        if not path.is_file() or expected_name not in path.read_text(encoding="utf-8"):
            raise RuntimeError(
                f"Инструкция {path} должна содержать актуальное имя {expected_name}"
            )
