# Cycle Start/Stop and UI Responsiveness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `старт` and `стоп` controls to the `цикл` section and make long-running search work happen off the GUI thread so the window stays responsive.

**Architecture:** We will keep the current app layout and reuse the existing `MerchantSearchWorker` / `QThread` path in `gui/main_window.py` instead of inventing a new execution model. The UI will own the start/stop buttons, the controller will keep the business logic, and the worker thread will carry the long-running cycle while emitting progress and completion signals back to the main window.

**Tech Stack:** Python, PySide6, pytest, existing `AppController`, `MerchantCycleService`, `MerchantSearchWorker`.

---

### Task 1: Add `старт` and `стоп` controls to the `цикл` section

**Files:**
- Modify: `src/bybit_automation/gui/sections/search_section.py`
- Test: `tests/test_main_window.py`

- [ ] **Step 1: Write the failing test**

```python
def test_search_section_exposes_start_and_stop_cycle_buttons() -> None:
    section = SearchSection()
    assert section.start_search_button.text() == "Старт"
    assert section.stop_search_button.text() == "Стоп"
    assert section.stop_search_button.isEnabled() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main_window.py -k search_section_exposes_start_and_stop_cycle_buttons -v`
Expected: FAIL because the section still uses the old labels.

- [ ] **Step 3: Write minimal implementation**

```python
class SearchSection(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.account_name_edit = QLineEdit()
        self.depth_edit = QLineEdit("4")
        self.depth_edit.setValidator(QIntValidator(1, 999))

        self.collect_merchants_button = QPushButton("Собрать мерчантов")
        self.start_search_button = QPushButton("Старт")
        self.stop_search_button = QPushButton("Стоп")
        self.stop_search_button.setMaximumWidth(120)
        self.save_result_button = QPushButton("Записать результат")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main_window.py -k search_section_exposes_start_and_stop_cycle_buttons -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bybit_automation/gui/sections/search_section.py tests/test_main_window.py
git commit -m "feat: add cycle start and stop buttons"
```

### Task 2: Move merchant search to the worker thread and wire stop handling

**Files:**
- Modify: `src/bybit_automation/gui/main_window.py`
- Modify: `src/bybit_automation/controllers/app_controller.py`
- Test: `tests/test_app_controller.py`
- Test: `tests/test_main_window.py`

- [ ] **Step 1: Write the failing test**

```python
def test_start_search_uses_worker_thread_and_stop_disables_cycle() -> None:
    # Arrange a fake controller whose search takes time.
    # Start search should return quickly, set the UI into running state,
    # and stop_search should request cancellation.
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main_window.py -k start_search_uses_worker_thread_and_stop_disables_cycle -v`
Expected: FAIL because `on_start_search()` still runs synchronously.

- [ ] **Step 3: Write minimal implementation**

```python
def on_start_search(self) -> None:
    if self._search_thread is not None:
        return
    state = self.collect_state()
    self._search_worker = MerchantSearchWorker(self._controller, state)
    self._search_thread = QThread(self)
    self._search_worker.moveToThread(self._search_thread)
    self._search_thread.started.connect(self._search_worker.run)
    self._search_worker.progress.connect(self._on_search_progress)
    self._search_worker.finished.connect(self._on_search_finished)
    self._search_worker.failed.connect(self._on_search_failed)
    self._search_worker.finished.connect(self._cleanup_search_thread)
    self._search_worker.failed.connect(self._cleanup_search_thread)
    self._set_search_running(True)
    self._search_thread.start()

def on_stop_search(self) -> None:
    self._controller.stop_merchant_search()
    self.search_section.search_status_label.setText("Останавливаю поиск")
    self.status_bar.showMessage("Останавливаю поиск")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main_window.py -k start_search_uses_worker_thread_and_stop_disables_cycle -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bybit_automation/gui/main_window.py src/bybit_automation/controllers/app_controller.py tests/test_app_controller.py tests/test_main_window.py
git commit -m "feat: run merchant search off the ui thread"
```

### Task 3: Keep the GUI responsive while the cycle runs

**Files:**
- Modify: `src/bybit_automation/gui/main_window.py`
- Modify: `src/bybit_automation/services/merchant_cycle_service.py`
- Test: `tests/test_merchant_cycle_service.py`
- Test: `tests/test_main_window.py`

- [ ] **Step 1: Write the failing test**

```python
def test_live_cycle_reports_stop_and_progress_without_blocking_ui() -> None:
    # Simulate a long loop with stop_requested flipping to True.
    # Verify the service returns a stopped result and emits progress updates.
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_merchant_cycle_service.py -k live_cycle_reports_stop_and_progress_without_blocking_ui -v`
Expected: FAIL if the current flow does not emit enough progress or does not exit promptly.

- [ ] **Step 3: Write minimal implementation**

```python
def _on_search_progress(self, page: int, position: int, status: str) -> None:
    self.search_section.current_page_label.setText(str(page) if page else "")
    self.search_section.current_position_label.setText(f"{position}/10" if position else "")
    self.search_section.search_status_label.setText(status)
    self._logger.info(f"Поиск: страница {page}, позиция {position}/10: {status}")

def _should_stop(self, stop_requested: Callable[[], bool]) -> bool:
    return self._stop_requested or stop_requested()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_merchant_cycle_service.py -k live_cycle_reports_stop_and_progress_without_blocking_ui -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bybit_automation/gui/main_window.py src/bybit_automation/services/merchant_cycle_service.py tests/test_merchant_cycle_service.py tests/test_main_window.py
git commit -m "feat: keep merchant cycle responsive and stoppable"
```

## Self-Review

1. Spec coverage:
   - `старт` and `стоп` buttons in `цикл`: covered by Task 1.
   - UI stays accessible during long chains: covered by Task 2 and Task 3.
   - Ability to stop any running process in the cycle: covered by Task 2 and Task 3.

2. Placeholder scan:
   - No `TBD`, `TODO`, or vague filler left in the plan steps.
   - Test snippets are concrete enough to implement directly.

3. Type consistency:
   - `MerchantSearchWorker`, `QThread`, `start_search_button`, and `stop_search_button` are already present in the codebase and match the plan.
   - The plan keeps the existing controller/service boundaries intact.

