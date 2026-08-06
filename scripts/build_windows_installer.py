from __future__ import annotations

import importlib.metadata
import platform
import shutil
import struct
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bybit_automation.packaging.portable_chrome import (  # noqa: E402
    PortableChromeManifest,
    prepare_portable_chrome,
)
from bybit_automation.packaging.release import (  # noqa: E402
    INNO_SETUP_VERSION,
    PYINSTALLER_VERSION,
    create_release_manifest,
    find_inno_setup_compiler,
    read_inno_setup_version,
    require_tool_version,
    require_windows_x64_build,
    validate_release_inputs,
    validate_release_instruction_versions,
    write_release_manifest,
)


def _project_version() -> str:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def _run(command: list[str]) -> None:
    print(f"Выполняю: {subprocess.list2cmdline(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    chrome_manifest_path = ROOT / "packaging" / "chrome-for-testing.json"
    installed_pyinstaller = importlib.metadata.version("pyinstaller")
    if installed_pyinstaller != PYINSTALLER_VERSION:
        raise RuntimeError(
            f"Нужен PyInstaller {PYINSTALLER_VERSION}, установлен {installed_pyinstaller}. "
            "Выполни: python -m pip install -e .[build]"
        )
    iscc = find_inno_setup_compiler()
    installed_inno_setup = read_inno_setup_version(iscc)
    require_tool_version(
        "Inno Setup",
        actual=installed_inno_setup,
        expected=INNO_SETUP_VERSION,
    )
    app_version = _project_version()
    require_windows_x64_build(
        machine=platform.machine(),
        pointer_bits=struct.calcsize("P") * 8,
    )
    validate_release_instruction_versions(ROOT, app_version=app_version)
    chrome_manifest = PortableChromeManifest.load(chrome_manifest_path)

    _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(ROOT / "packaging" / "BybitAutomation.spec"),
        ]
    )

    release_runtime_root = (ROOT / "build" / "release-runtime").resolve()
    if not release_runtime_root.is_relative_to((ROOT / "build").resolve()):
        raise RuntimeError(f"Небезопасный каталог временной сборки: {release_runtime_root}")
    if release_runtime_root.exists():
        shutil.rmtree(release_runtime_root)
    release_chrome_destination = ROOT / "build" / "release-runtime" / "chrome-for-testing"
    release_chrome_executable = prepare_portable_chrome(
        chrome_manifest_path,
        release_chrome_destination,
    )
    validate_release_inputs(ROOT, chrome_executable=release_chrome_executable)

    packaged_chrome_destination = (
        ROOT / "dist" / "BybitAutomation" / "runtime" / "chrome-for-testing"
    )
    if packaged_chrome_destination.exists():
        shutil.rmtree(packaged_chrome_destination)
    shutil.copytree(release_chrome_destination, packaged_chrome_destination)

    app_executable = ROOT / "dist" / "BybitAutomation" / "BybitAutomation.exe"
    chrome_executable = packaged_chrome_destination / chrome_manifest.executable_relative_path
    app_manifest = create_release_manifest(
        app_version=app_version,
        python_version=platform.python_version(),
        pyinstaller_version=installed_pyinstaller,
        inno_setup_version=installed_inno_setup,
        playwright_version=importlib.metadata.version("playwright"),
        chrome_version=chrome_manifest.version,
        app_executable=app_executable,
        chrome_executable=chrome_executable,
    )
    write_release_manifest(
        ROOT / "dist" / "BybitAutomation" / "release-manifest.json",
        app_manifest,
    )

    _run(
        [
            str(iscc),
            f"/DMyAppVersion={app_version}",
            str(ROOT / "packaging" / "BybitAutomation.iss"),
        ]
    )
    installer = ROOT / "dist" / "installer" / f"BybitAutomation-Setup-{app_version}.exe"
    release_manifest = create_release_manifest(
        app_version=app_version,
        python_version=platform.python_version(),
        pyinstaller_version=installed_pyinstaller,
        inno_setup_version=installed_inno_setup,
        playwright_version=importlib.metadata.version("playwright"),
        chrome_version=chrome_manifest.version,
        app_executable=app_executable,
        chrome_executable=chrome_executable,
        installer=installer,
    )
    write_release_manifest(ROOT / "dist" / "installer" / "release-manifest.json", release_manifest)
    print(f"Установщик готов: {installer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
