# GitHub Release 0.1.0: checklist и черновик

Этот документ предназначен разработчику. Релиз не публиковать без отдельного
разрешения пользователя и успешной приёмки на чистой Windows 10/11 x64.

## Файлы релиза

В GitHub Release загрузить только два подготовленных файла:

1. `dist/installer/BybitAutomation-Setup-0.1.0.exe`
2. `dist/installer/release-manifest.json`

Не загружать профили браузера, `data/`, `runtime/`, `build/`, распакованный
`dist/BybitAutomation/` или отдельный ZIP проекта.

## Проверка перед публикацией

1. Убедиться, что рабочее дерево Git чистое:

   ```powershell
   git status --short
   ```

2. Запустить тесты:

   ```powershell
   python -m pytest -q
   ```

3. Собрать релиз одной командой:

   ```powershell
   python scripts/build_windows_installer.py
   ```

4. Получить контрольную сумму установщика:

   ```powershell
   Get-FileHash -Algorithm SHA256 dist\installer\BybitAutomation-Setup-0.1.0.exe
   ```

5. Сравнить SHA-256 с полем `files.installer.sha256` в
   `dist/installer/release-manifest.json`.
6. Выполнить приёмку на чистой Windows по утверждённому сценарию.
7. После успешной приёмки получить SHA проверенного коммита:

   ```powershell
   git rev-parse HEAD
   ```

8. Только после отдельного разрешения пользователя создать тег `v0.1.0` на
   этом коммите и проверить привязку:

   ```powershell
   git tag -a v0.1.0 -m "Bybit Automation 0.1.0"
   git rev-parse HEAD
   git rev-list -n 1 v0.1.0
   ```

   Две последние команды должны вернуть совпадающие SHA коммита.
9. GitHub Release создавать строго из тега `v0.1.0`, а не из произвольной
   ветки или другого коммита.
10. До отдельного подтверждения пользователя релиз, ветку и тег не публиковать.

## Черновик описания релиза

**Заголовок:** `Bybit Automation 0.1.0`

Windows 10/11 x64 установщик Bybit Automation. Python и Portable Chrome входят
в установщик и отдельно не требуются. После установки запустите приложение из
меню «Пуск», выберите `Portable Chrome 150` для браузера и автоматизации, затем
нажмите «Открыть выбранный браузер».

Основная пользовательская инструкция устанавливается вместе с программой в
файле `запуск.txt`.
