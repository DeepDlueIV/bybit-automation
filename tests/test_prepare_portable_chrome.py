from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from bybit_automation.packaging.portable_chrome import (
    extract_zip_safely,
    prepare_portable_chrome,
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_prepare_portable_chrome_downloads_verifies_and_extracts_once(tmp_path: Path) -> None:
    source_zip = tmp_path / "source.zip"
    executable_payload = b"portable-chrome"
    with zipfile.ZipFile(source_zip, "w") as archive:
        archive.writestr("chrome-win64/chrome.exe", executable_payload)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": "150.0.7871.124",
                "platform": "win64",
                "url": "https://example.invalid/chrome.zip",
                "archive_sha256": hashlib.sha256(source_zip.read_bytes()).hexdigest(),
                "executable_relative_path": "chrome-win64/chrome.exe",
                "executable_sha256": sha256_bytes(executable_payload),
            }
        ),
        encoding="utf-8",
    )
    downloads: list[str] = []

    def fake_download(url: str, output: Path) -> None:
        downloads.append(url)
        shutil.copyfile(source_zip, output)

    destination = tmp_path / "runtime" / "chrome-for-testing"

    executable = prepare_portable_chrome(manifest_path, destination, downloader=fake_download)
    repeated = prepare_portable_chrome(manifest_path, destination, downloader=fake_download)

    assert executable == destination / "chrome-win64" / "chrome.exe"
    assert executable.read_bytes() == executable_payload
    assert repeated == executable
    assert downloads == ["https://example.invalid/chrome.zip"]


def test_extract_zip_safely_rejects_path_outside_destination(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")

    with pytest.raises(RuntimeError, match="небезопасный путь"):
        extract_zip_safely(archive_path, tmp_path / "destination")

    assert not (tmp_path / "outside.txt").exists()
