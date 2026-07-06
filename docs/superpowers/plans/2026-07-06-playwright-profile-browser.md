# Playwright Profile Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Playwright profile` usable as a normal interactive browser profile for manual proxy/extension setup while keeping Playwright automation on the same profile.

**Architecture:** Add explicit browser launch configuration to `PlaywrightBrowserDriver`: prefer installed Google Chrome for persistent profile, fall back to Playwright bundled Chromium when Chrome is unavailable, and expose a controller/GUI action to open the Playwright profile without starting the cycle. Keep Incogniton UIA unchanged.

**Tech Stack:** Python 3.11+, PySide6, Playwright sync API, pytest.

## Global Constraints

- Windows-only project.
- Do not use Incogniton Playwright/CDP because CDP is blocked on the current free Incogniton plan.
- Do not change existing UIA click logic or advertisement form logic unless required for this feature.
- Use `from __future__ import annotations` in new Python files.
- Use Russian user-facing log messages.

---

### Task 1: Browser Channel Selection

**Files:**
- Modify: `src/bybit_automation/infrastructure/playwright_browser_driver.py`
- Test: `tests/test_playwright_browser_driver.py`

**Interfaces:**
- Produces: `PlaywrightBrowserDriver._launch_persistent_context_kwargs() -> dict[str, Any]`
- Produces: `PlaywrightBrowserDriver.open_profile(window_title: str) -> None`

- [ ] **Step 1: Write failing tests**

Add tests that verify `Playwright profile` prefers Chrome channel and preserves existing persistent context settings.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_playwright_browser_driver.py -v`

Expected: FAIL because `_launch_persistent_context_kwargs` does not exist.

- [ ] **Step 3: Implement minimal browser launch configuration**

Add a helper that returns `headless`, `viewport`, `locale`, and `channel="chrome"` for `AutomationMode.PLAYWRIGHT_PROFILE`. Use these kwargs in `launch_persistent_context`.

- [ ] **Step 4: Add an interactive profile opener**

Add `open_profile()` that ensures the context and opens `https://www.bybit.com/ru-RU/p2p/sell/USDT/RUB` only if no page exists.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_playwright_browser_driver.py -v`

Expected: PASS.

### Task 2: GUI Open Profile Action

**Files:**
- Modify: `src/bybit_automation/controllers/app_controller.py`
- Modify: `src/bybit_automation/gui/sections/browser_section.py`
- Modify: `src/bybit_automation/gui/main_window.py`
- Test: `tests/test_app_controller.py`
- Test: `tests/test_main_window.py`

**Interfaces:**
- Consumes: `PlaywrightBrowserDriver.open_profile(window_title: str) -> None`
- Produces: `AppController.open_selected_browser_profile(state: AppState) -> bool`

- [ ] **Step 1: Write failing controller test**

Verify that the controller calls the service for selected automation mode without running the cycle.

- [ ] **Step 2: Add button test**

Verify `BrowserSection` exposes a button with text `Открыть Playwright-профиль`.

- [ ] **Step 3: Implement controller method**

Route to the selected browser service and call `open_profile` if available. Log clear Russian error if unsupported.

- [ ] **Step 4: Implement GUI button wiring**

Add the button to Browser section and connect it to controller action in `MainWindow`.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_app_controller.py tests/test_main_window.py tests/test_playwright_browser_driver.py -v`

Expected: PASS.

### Task 3: Verification

**Files:**
- No code changes expected.

- [ ] **Step 1: Run lint/tests**

Run: `pytest`

Run: `ruff check src\ tests\`

- [ ] **Step 2: Live smoke-check if browser window is available**

Open GUI, select `Playwright profile`, click `Открыть Playwright-профиль`, verify the browser opens without starting the cycle and can navigate to `https://example.com` and Chrome Web Store.
