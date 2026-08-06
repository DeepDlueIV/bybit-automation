from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import pytest


def test_release_inputs_require_runtime_browser_and_user_resources(tmp_path: Path) -> None:
    from bybit_automation.packaging.release import validate_release_inputs

    (tmp_path / "sound").mkdir()
    (tmp_path / "sound" / "Alarm09.wav").touch()
    (tmp_path / "запуск.txt").touch()

    with pytest.raises(RuntimeError, match="Portable Chrome"):
        validate_release_inputs(tmp_path)


def test_release_manifest_records_versions_and_file_hashes(tmp_path: Path) -> None:
    from bybit_automation.packaging.release import create_release_manifest

    app_executable = tmp_path / "BybitAutomation.exe"
    chrome_executable = tmp_path / "runtime" / "chrome.exe"
    installer = tmp_path / "BybitAutomation-Setup-0.1.0.exe"
    chrome_executable.parent.mkdir(parents=True)
    internal = tmp_path / "_internal"
    internal.mkdir()
    (internal / "python314.dll").write_bytes(b"python")
    (chrome_executable.parent / "resources.pak").write_bytes(b"resources")
    app_executable.write_bytes(b"app")
    chrome_executable.write_bytes(b"chrome")
    installer.write_bytes(b"installer")

    manifest = create_release_manifest(
        app_version="0.1.0",
        python_version="3.14.3",
        pyinstaller_version="6.21.0",
        inno_setup_version="6.7.3",
        playwright_version="1.61.0",
        chrome_version="150.0.7871.124",
        app_executable=app_executable,
        chrome_executable=chrome_executable,
        installer=installer,
    )

    assert manifest["versions"] == {
        "application": "0.1.0",
        "python": "3.14.3",
        "pyinstaller": "6.21.0",
        "inno_setup": "6.7.3",
        "playwright": "1.61.0",
        "portable_chrome": "150.0.7871.124",
    }
    assert manifest["files"]["application"]["sha256"] == hashlib.sha256(b"app").hexdigest()
    assert manifest["files"]["portable_chrome"]["sha256"] == hashlib.sha256(b"chrome").hexdigest()
    assert manifest["files"]["installer"]["sha256"] == hashlib.sha256(b"installer").hexdigest()
    assert manifest["files"]["application_runtime"]["file_count"] == 1
    assert manifest["files"]["application_runtime"]["size"] == len(b"python")
    assert manifest["files"]["portable_chrome_runtime"]["file_count"] == 2
    assert len(manifest["files"]["application_runtime"]["sha256"]) == 64


def test_write_release_manifest_uses_utf8_json(tmp_path: Path) -> None:
    from bybit_automation.packaging.release import write_release_manifest

    output = tmp_path / "release-manifest.json"
    payload = {"product": "Bybit Automation", "note": "установщик"}

    write_release_manifest(output, payload)

    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_pyinstaller_spec_builds_onedir_gui_and_collects_playwright_data() -> None:
    spec = Path("packaging/BybitAutomation.spec").read_text(encoding="utf-8")

    assert "ROOT = Path(SPECPATH).parent\n" in spec
    assert "Path(SPECPATH).parent.parent" not in spec
    assert 'collect_data_files("playwright")' in spec
    assert "exclude_binaries=True" in spec
    assert "console=False" in spec
    assert "COLLECT(" in spec
    assert 'name="BybitAutomation"' in spec


def test_inno_script_bundles_runtime_resources_and_shortcuts() -> None:
    script = Path("packaging/BybitAutomation.iss").read_text(encoding="utf-8")

    assert "{localappdata}\\BybitAutomation" in script
    assert 'Source: "..\\dist\\BybitAutomation\\*"' in script
    assert 'Source: "..\\runtime\\chrome-for-testing\\*"' not in script
    assert 'Source: "..\\sound\\Alarm09.wav"' in script
    assert 'Source: "..\\запуск.txt"' in script
    assert 'Filename: "{app}\\BybitAutomation.exe"' in script
    assert 'Filename: "{app}"' in script
    assert "PrivilegesRequired=lowest" in script
    assert "SaveStringsToUTF8File(" in script
    assert "SaveStringToFile(" not in script
    assert "{app}\\ГДЕ_НАХОДЯТСЯ_ФАЙЛЫ.txt" in script


def test_build_dependencies_are_pinned() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'pyinstaller==6.21.0' in pyproject


def test_build_script_prepares_browser_and_passes_project_version_to_inno() -> None:
    script = Path("scripts/build_windows_installer.py").read_text(encoding="utf-8")
    inno = Path("packaging/BybitAutomation.iss").read_text(encoding="utf-8")

    assert script.index("prepare_portable_chrome(") < script.index("validate_release_inputs(")
    assert 'ROOT / "build" / "release-runtime" / "chrome-for-testing"' in script
    assert "shutil.copytree(" in script
    assert 'ROOT / "dist" / "BybitAutomation" / "runtime" / "chrome-for-testing"' in script
    assert 'f"/DMyAppVersion={app_version}"' in script
    assert "#ifndef MyAppVersion" in inno


def test_build_rejects_unexpected_inno_setup_version() -> None:
    from bybit_automation.packaging.release import require_tool_version

    with pytest.raises(RuntimeError, match="ожидалась 6.7.3"):
        require_tool_version("Inno Setup", actual="6.7.2", expected="6.7.3")


def test_build_rejects_non_x64_python() -> None:
    from bybit_automation.packaging.release import require_windows_x64_build

    with pytest.raises(RuntimeError, match="Windows x64"):
        require_windows_x64_build(machine="ARM64", pointer_bits=64)


def test_release_instructions_reject_stale_installer_version(tmp_path: Path) -> None:
    from bybit_automation.packaging.release import validate_release_instruction_versions

    (tmp_path / "docs").mkdir()
    (tmp_path / "запуск.txt").write_text(
        "BybitAutomation-Setup-0.1.0.exe",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "build-windows-installer.md").write_text(
        "BybitAutomation-Setup-0.1.0.exe",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="BybitAutomation-Setup-0.2.0.exe"):
        validate_release_instruction_versions(tmp_path, app_version="0.2.0")


def test_release_instructions_use_project_version() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    app_version = str(project["project"]["version"])
    expected_name = f"BybitAutomation-Setup-{app_version}.exe"
    instruction = Path("запуск.txt").read_text(encoding="utf-8")
    build_instruction = Path("docs/build-windows-installer.md").read_text(encoding="utf-8")

    assert expected_name in instruction
    assert expected_name in build_instruction
    assert "BybitAutomation-Setup.exe" not in instruction
