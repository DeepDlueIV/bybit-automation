from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class PortableChromeManifest:
    version: str
    platform: str
    url: str
    archive_sha256: str
    executable_relative_path: Path
    executable_sha256: str

    @classmethod
    def load(cls, path: Path) -> "PortableChromeManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            version=str(payload["version"]),
            platform=str(payload["platform"]),
            url=str(payload["url"]),
            archive_sha256=str(payload["archive_sha256"]).lower(),
            executable_relative_path=Path(str(payload["executable_relative_path"])),
            executable_sha256=str(payload["executable_sha256"]).lower(),
        )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, output: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "BybitAutomation/portable-chrome"})
    with urllib.request.urlopen(request, timeout=60) as response, output.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024)


def extract_zip_safely(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination_root):
                raise RuntimeError(f"ZIP содержит небезопасный путь: {member.filename}")
            unix_mode = member.external_attr >> 16
            if unix_mode & 0o170000 == 0o120000:
                raise RuntimeError(f"ZIP содержит недопустимую символическую ссылку: {member.filename}")
        archive.extractall(destination)


def prepare_portable_chrome(
    manifest_path: Path,
    destination: Path,
    *,
    downloader: Callable[[str, Path], None] = _download,
) -> Path:
    manifest = PortableChromeManifest.load(manifest_path)
    executable = destination / manifest.executable_relative_path
    if executable.is_file() and file_sha256(executable) == manifest.executable_sha256:
        return executable
    if destination.exists():
        raise RuntimeError(
            f"Каталог Portable Chrome уже существует, но не прошёл SHA-256: {destination}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    archive_path = destination.parent / f".chrome-{manifest.version}-{uuid.uuid4().hex}.zip"
    staging = destination.parent / f".{destination.name}-{uuid.uuid4().hex}.tmp"
    try:
        downloader(manifest.url, archive_path)
        actual_archive_sha256 = file_sha256(archive_path)
        if actual_archive_sha256 != manifest.archive_sha256:
            raise RuntimeError(
                "SHA-256 архива Portable Chrome не совпадает: "
                f"ожидался {manifest.archive_sha256}, получен {actual_archive_sha256}"
            )
        extract_zip_safely(archive_path, staging)
        staged_executable = staging / manifest.executable_relative_path
        if not staged_executable.is_file():
            raise RuntimeError(f"В архиве отсутствует Chrome: {manifest.executable_relative_path}")
        actual_executable_sha256 = file_sha256(staged_executable)
        if actual_executable_sha256 != manifest.executable_sha256:
            raise RuntimeError(
                "SHA-256 chrome.exe не совпадает: "
                f"ожидался {manifest.executable_sha256}, получен {actual_executable_sha256}"
            )
        os.replace(staging, destination)
        return executable
    finally:
        archive_path.unlink(missing_ok=True)
        if staging.exists():
            shutil.rmtree(staging)
