# Сборка Windows-установщика

Этот документ нужен разработчику релиза. Обычному пользователю достаточно
корневого файла `запуск.txt` и готового установщика.

## Инструменты

Из корня проекта:

```powershell
python -m pip install -e ".[build]"
winget install --id JRSoftware.InnoSetup -e --version 6.7.3 --accept-package-agreements --accept-source-agreements
```

## Сборка

Запустить одну команду:

```powershell
python scripts/build_windows_installer.py
```

Скрипт для каждой релизной сборки заново скачивает закреплённый Portable Chrome
во временный каталог `build/`, проверяет SHA-256 архива и `chrome.exe`, затем
выполняет обе стадии сборки. Каталог `runtime/` из рабочей копии в установщик не
попадает.

Результаты:

- `dist/BybitAutomation/` — распакованное приложение PyInstaller;
- `dist/installer/BybitAutomation-Setup-0.1.0.exe` — установщик;
- `dist/installer/release-manifest.json` — версии, размеры и SHA-256.

Папки `build/` и `dist/` не коммитятся. Установщик публикуется через GitHub Releases.
