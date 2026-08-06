# Git History Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подготовить компактный и безопасный Git-репозиторий без браузерных профилей, логов, cookies и других runtime-файлов, сохранив текущую рабочую папку и всю её папку `data/` без изменений.

**Architecture:** Сначала текущая ветка перестаёт отслеживать runtime-файлы, но сами файлы остаются на диске. Затем полная история очищается только в отдельном зеркале репозитория, из которого создаётся контрольный клон. Исходная рабочая папка и рабочие режимы браузера не переписываются, а публикация в GitHub выполняется только после отдельного подтверждения пользователя.

**Tech Stack:** Git, `git-filter-repo`, PowerShell 7/Windows PowerShell, Python `pip`, pytest.

## Global Constraints

- Существующие режимы `System Chrome extensions profile` и `System Chrome extensions profile (restart recovery)` не изменять.
- Рабочая папка `data/` и браузерный профиль должны остаться на диске и продолжить работать локально.
- Не переносить браузерный профиль в новый репозиторий, установщик или GitHub.
- Не выполнять push или force-push без отдельного подтверждения пользователя.
- Каждый логический результат фиксировать отдельным коммитом.
- Этап завершается только после успешного клонирования очищенного зеркала и проверки его содержимого.

---

### Task 1: Защитная копия и исходный отпечаток

**Files:**
- Create outside repository: `%USERPROFILE%\BybitAutomationBackups\<timestamp>\bybit-automation-before-cleanup.bundle`
- Create outside repository: `%USERPROFILE%\BybitAutomationBackups\<timestamp>\source-snapshot\`
- Create outside repository: `%USERPROFILE%\BybitAutomationBackups\<timestamp>\baseline.txt`

**Interfaces:**
- Consumes: текущий репозиторий на ветке `bybit-playwright`.
- Produces: полный Git bundle, копию исходников без `.git` и `data`, текстовый исходный отпечаток.

- [ ] **Step 1: Проверить свободное место и состояние Git**

Run:

```powershell
$repo = (Get-Location).Path
$drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($repo).TrimEnd(':\'))
git status --short --untracked-files=no
git count-objects -vH
"Свободно: {0:N2} GiB" -f ($drive.Free / 1GB)
```

Expected: свободно не менее `10 GiB`; изменения относятся к runtime-файлам внутри `data/`.

- [ ] **Step 2: Создать каталог резервной копии**

Run:

```powershell
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $env:USERPROFILE "BybitAutomationBackups\$timestamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$backup | Set-Content -LiteralPath (Join-Path $env:TEMP 'bybit-automation-backup-path.txt')
```

Expected: создан отдельный каталог вне рабочей папки и OneDrive-репозитория.

- [ ] **Step 3: Создать полный Git bundle**

Run:

```powershell
$backup = Get-Content -LiteralPath (Join-Path $env:TEMP 'bybit-automation-backup-path.txt')
git bundle create (Join-Path $backup 'bybit-automation-before-cleanup.bundle') --all
git bundle verify (Join-Path $backup 'bybit-automation-before-cleanup.bundle')
```

Expected: `git bundle verify` подтверждает полноценный bundle со всеми refs.

- [ ] **Step 4: Скопировать исходники без профилей и служебных каталогов**

Run:

```powershell
$backup = Get-Content -LiteralPath (Join-Path $env:TEMP 'bybit-automation-backup-path.txt')
$snapshot = Join-Path $backup 'source-snapshot'
robocopy . $snapshot /E /XD .git data .pytest_cache .ruff_cache __pycache__ build dist /XF *.pyc *.pyo app.log
if ($LASTEXITCODE -gt 7) { throw "robocopy завершился с кодом $LASTEXITCODE" }
```

Expected: исходники, документация, расширение и звук скопированы; `.git` и `data` отсутствуют.

- [ ] **Step 5: Записать исходный отпечаток**

Run:

```powershell
$backup = Get-Content -LiteralPath (Join-Path $env:TEMP 'bybit-automation-backup-path.txt')
@(
  "timestamp=$(Get-Date -Format o)"
  "repo=$((Get-Location).Path)"
  "branch=$(git branch --show-current)"
  "head=$(git rev-parse HEAD)"
  "remote=$(git remote get-url origin)"
  "tracked_files=$((git ls-files).Count)"
  "tracked_data_files=$((git ls-files data).Count)"
  (git count-objects -vH)
) | Set-Content -LiteralPath (Join-Path $backup 'baseline.txt') -Encoding UTF8
```

Expected: `baseline.txt` содержит commit, remote, число файлов и размер Git до очистки.

### Task 2: Прекратить отслеживание runtime-файлов

**Files:**
- Modify: `.gitignore`
- Untrack without deleting: `data/`, `src/bybit_automation.egg-info/`, все `__pycache__/` и `*.pyc`.

**Interfaces:**
- Consumes: защитную копию из Task 1.
- Produces: обычный коммит, после которого новые runtime-файлы не попадают в Git.

- [ ] **Step 1: Расширить `.gitignore`**

Required content:

```gitignore
# Runtime-данные, настройки, логи и браузерные профили
data/

# Локальные окружения Python
.venv/
venv/

# Python и тестовые кэши
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/

# Результаты сборки
build/
dist/
*.egg-info/

# Диагностические результаты браузеров
playwright-report/
test-results/

# Локальные логи
*.log
```

- [ ] **Step 2: Удалить runtime-файлы только из индекса Git**

Run:

```powershell
git rm -r --cached --ignore-unmatch data src/bybit_automation.egg-info
$generated = git ls-files | Where-Object { $_ -match '(^|/)__pycache__/|\.py[co]$' }
foreach ($path in $generated) { git rm --cached --ignore-unmatch -- $path }
```

Expected: Git показывает удаления, но `Test-Path data` возвращает `True`.

- [ ] **Step 3: Проверить индекс и сохранность профиля**

Run:

```powershell
if ((git ls-files data).Count -ne 0) { throw 'data всё ещё отслеживается Git' }
if (-not (Test-Path -LiteralPath 'data')) { throw 'локальная папка data потеряна' }
git check-ignore -v data/app.log
git diff --cached --stat
```

Expected: `data/` игнорируется, локальная папка существует, в индексе только ожидаемая очистка.

- [ ] **Step 4: Зафиксировать прекращение отслеживания**

Run:

```powershell
git add .gitignore
git commit -m "chore: stop tracking runtime browser data"
```

Expected: создан один коммит; файлы `data/` физически остаются на месте.

### Task 3: Построить очищенное зеркало истории

**Files:**
- Create outside repository: `%USERPROFILE%\BybitAutomationBackups\<timestamp>\cleaned-repository.git\`

**Interfaces:**
- Consumes: текущий репозиторий после Task 2 и сохранённый bundle.
- Produces: отдельное bare-зеркало без runtime-истории.

- [ ] **Step 1: Установить и проверить `git-filter-repo`**

Run:

```powershell
python -m pip install --user git-filter-repo
python -m git_filter_repo --version
```

Expected: команда печатает версию `git-filter-repo`.

- [ ] **Step 2: Создать локальное зеркало**

Run:

```powershell
$backup = Get-Content -LiteralPath (Join-Path $env:TEMP 'bybit-automation-backup-path.txt')
$mirror = Join-Path $backup 'cleaned-repository.git'
git clone --mirror . $mirror
```

Expected: создан bare-репозиторий; исходная рабочая папка не изменилась.

- [ ] **Step 3: Удалить runtime-файлы из всех коммитов зеркала**

Run inside `$mirror`:

```powershell
python -m git_filter_repo --force --invert-paths `
  --path data/ `
  --path src/bybit_automation.egg-info/ `
  --path-glob '*/__pycache__/*' `
  --path-glob '*.pyc' `
  --path-glob '*.pyo' `
  --path build/ `
  --path dist/
```

Expected: команда переписывает только отдельное зеркало; `data/` отсутствует во всех refs.

### Task 4: Проверить очищенный репозиторий

**Files:**
- Create outside repository: `%USERPROFILE%\BybitAutomationBackups\<timestamp>\clean-clone\`
- Create outside repository: `%USERPROFILE%\BybitAutomationBackups\<timestamp>\verification.txt`

**Interfaces:**
- Consumes: очищенное зеркало из Task 3.
- Produces: контрольный клон и доказательство готовности к будущему push.

- [ ] **Step 1: Создать контрольный клон**

Run:

```powershell
$backup = Get-Content -LiteralPath (Join-Path $env:TEMP 'bybit-automation-backup-path.txt')
$mirror = Join-Path $backup 'cleaned-repository.git'
$clone = Join-Path $backup 'clean-clone'
git clone $mirror $clone
```

Expected: клон создаётся без зависания; рабочая ветка доступна.

- [ ] **Step 2: Проверить отсутствие runtime-файлов во всей истории**

Run inside `$mirror`:

```powershell
$runtimeObjects = git rev-list --objects --all | Select-String -Pattern ' data/|/__pycache__/|\.py[co]$|\.egg-info/'
if ($runtimeObjects) { throw 'В очищенной истории остались runtime-файлы' }
```

Expected: переменная `$runtimeObjects` пуста.

- [ ] **Step 3: Проверить максимальный размер файла в истории**

Run inside `$mirror`:

```powershell
$objects = git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)'
$large = $objects | Where-Object {
  $parts = $_ -split ' ', 3
  $parts[0] -eq 'blob' -and [int64]$parts[1] -gt 50MB
}
if ($large) { $large; throw 'Найдены файлы больше 50 MiB' }
```

Expected: файлов больше `50 MiB` нет.

- [ ] **Step 4: Запустить тесты из контрольного клона**

Run inside `$clone`:

```powershell
python -m pytest -q
```

Expected: тесты проходят; отсутствие старой `data/` не мешает импорту и тестам.

- [ ] **Step 5: Записать итог проверки и остановиться перед публикацией**

Run:

```powershell
$backup = Get-Content -LiteralPath (Join-Path $env:TEMP 'bybit-automation-backup-path.txt')
@(
  "timestamp=$(Get-Date -Format o)"
  "clean_head=$(git -C (Join-Path $backup 'clean-clone') rev-parse HEAD)"
  "tracked_data_files=$((git -C (Join-Path $backup 'clean-clone') ls-files data).Count)"
  (git -C (Join-Path $backup 'cleaned-repository.git') count-objects -vH)
  'push_performed=false'
) | Set-Content -LiteralPath (Join-Path $backup 'verification.txt') -Encoding UTF8
```

Expected: отчёт подтверждает очищенное зеркало и `push_performed=false`. Дальнейший push начинается только после подтверждения пользователя.
