from __future__ import annotations

from pathlib import Path

from bybit_automation.infrastructure.playwright_browser_driver import PlaywrightBrowserDriver
from bybit_automation.models.automation_mode import AutomationMode


class _Logger:
    def info(self, message: str) -> None:
        pass


class _Row:
    def __init__(self, text: str) -> None:
        self.text = text

    def inner_text(self, **kwargs) -> str:
        return self.text


class _Rows:
    def __init__(self, values: list[str]) -> None:
        self.values = values

    def count(self) -> int:
        return len(self.values)

    def nth(self, index: int) -> _Row:
        return _Row(self.values[index])


class _Page:
    def __init__(self, url: str, values: list[str]) -> None:
        self.url = url
        self.values = values
        self.goto_calls: list[str] = []

    def locator(self, selector: str) -> _Rows:
        assert selector == "table tbody tr"
        return _Rows(self.values)

    def goto(self, url: str, **kwargs) -> None:
        self.goto_calls.append(url)
        self.url = url


class _Context:
    def __init__(self, pages: list[_Page]) -> None:
        self.pages = pages
        self.created: _Page | None = None

    def new_page(self) -> _Page:
        self.created = _Page("about:blank", [])
        self.pages.append(self.created)
        return self.created


def _driver() -> PlaywrightBrowserDriver:
    return PlaywrightBrowserDriver(
        _Logger(),
        mode=AutomationMode.SYSTEM_CHROME_EXTENSIONS_PROFILE,
        user_data_dir=Path("profile"),
        artifacts_dir=Path("artifacts"),
    )


def test_no_records_is_empty_and_real_row_is_found(monkeypatch) -> None:
    driver = _driver()
    page = _Page(driver.ORDER_LIST_PREFIX + "processing", ["No Records"])
    context = _Context([page])
    monkeypatch.setattr(driver, "_ensure_context", lambda: context)

    empty = driver.detect_orders("")
    assert empty.found is False
    assert empty.row_count == 0

    page.values = ["Тип/Дата\nОрдер № 123\nСтатус: в процессе"]
    found = driver.detect_orders("")
    assert found.found is True
    assert found.row_count == 1


def test_order_page_is_opened_when_missing(monkeypatch) -> None:
    driver = _driver()
    context = _Context([])
    monkeypatch.setattr(driver, "_ensure_context", lambda: context)

    result = driver.detect_orders("")

    assert context.created is not None
    assert context.created.goto_calls == [driver.ORDER_LIST_URL]
    assert result.url == driver.ORDER_LIST_URL
