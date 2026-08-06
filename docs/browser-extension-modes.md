# Browser Extension Modes

Существующие режимы не менялись:

- `Incogniton UIA`
- `Incogniton Playwright/CDP`
- `Playwright profile`

Добавлены два отдельных режима для расширений.

## Playwright Chromium + extensions

Назначение: загрузка проектного распакованного bridge-расширения через Playwright Chromium.

Как подготовить:

1. Положи распакованное расширение в папку `bybiteye extension`.
2. Проверь, что внутри этой папки где-то есть `manifest.json`, например `bybiteye extension/<extension-id>/<version>/manifest.json`.
3. В приложении выбери браузер `Playwright Chromium` и автоматизацию `Playwright Chromium + extensions`.
4. Нажми `Открыть Playwright-профиль`.

Что делает режим:

- запускает отдельный профиль `data/playwright-chromium-extensions-profile`;
- если найден `manifest.json` внутри `bybiteye extension`, добавляет флаги `--disable-extensions-except` и `--load-extension` для папки с этим manifest;
- если папки `bybiteye extension` нет, fallback-путь остаётся `data/bridge-extension`;
- не использует и не меняет старый профиль `data/playwright-profile`.

## System Chrome extensions profile

Назначение: обычный Google Chrome с отдельным профилем, где пользовательские расширения ставятся вручную один раз.

Как подготовить:

1. В приложении выбери браузер `System Chrome` и автоматизацию `System Chrome extensions profile`.
2. Нажми `Открыть Playwright-профиль`.
3. В открывшемся Chrome вручную установи нужные расширения из Chrome Web Store или через `chrome://extensions`.
4. Закрой Chrome.
5. Снова открой этот же режим из приложения.

Что делает режим:

- запускает установленный Chrome с отдельным профилем `data/system-chrome-extensions-profile`;
- не передаёт `--disable-extensions`;
- сохраняет установленные вручную расширения между запусками;
- подключается к этому профилю через CDP для дальнейшей автоматизации.

## Важное ограничение

Обычный `Playwright profile` оставлен без изменений. В нём Chrome запускается с `--disable-extensions`, поэтому он не предназначен для установки расширений.
