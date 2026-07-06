from __future__ import annotations

from bybit_automation.infrastructure.windows_browser_finder import WindowsBrowserFinder


class FakeElement:
    def __init__(self, title: str, process_id: int) -> None:
        self._title = title
        self._process_id = process_id

    def window_text(self) -> str:
        return self._title

    def process_id(self) -> int:
        return self._process_id

    def descendants(self):
        return []


def test_find_windows_prefers_real_incogniton_browser_window(monkeypatch) -> None:
    elements = [
        FakeElement("Incogniton - Version 5.0.0.5", 10),
        FakeElement("Buy crypto with currency via Bybit P2P Crypto Trading - ILYA BB - 1", 20),
    ]

    class FakeDesktop:
        def __init__(self, backend: str) -> None:
            assert backend == "uia"

        def windows(self):
            return elements

    def fake_process_path(process_id: int) -> str:
        if process_id == 10:
            return r"C:\Users\DeepD\AppData\Local\Programs\incogniton\Incogniton.exe"
        if process_id == 20:
            return r"C:\Users\DeepD\AppData\Roaming\Incogniton\Incogniton\browser\146\win\chrome.exe"
        return ""

    monkeypatch.setattr("bybit_automation.infrastructure.windows_browser_finder.Desktop", FakeDesktop)
    monkeypatch.setattr("bybit_automation.infrastructure.windows_browser_finder.get_process_image_path", fake_process_path)

    finder = WindowsBrowserFinder()

    result = finder.find_windows("Incogniton")

    assert [window.title for window in result] == ["Buy crypto with currency via Bybit P2P Crypto Trading - ILYA BB - 1"]


def test_system_chrome_excludes_incogniton_and_playwright(monkeypatch) -> None:
    finder = WindowsBrowserFinder()
    paths = {
        1: r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        2: r"C:\Users\DeepD\AppData\Local\ms-playwright\chromium-1200\chrome-win64\chrome.exe",
        3: r"C:\Incogniton\browser\chrome.exe",
    }
    monkeypatch.setattr(
        "bybit_automation.infrastructure.windows_browser_finder.get_process_image_path",
        lambda process_id: paths[process_id],
    )

    assert finder._matches_window("System Chrome", "Chrome", 1) is True
    assert finder._matches_window("System Chrome", "Playwright Chromium", 2) is False
    assert finder._matches_window("System Chrome", "Incogniton", 3) is False


def test_playwright_chromium_matches_ms_playwright_browser(monkeypatch) -> None:
    finder = WindowsBrowserFinder()
    monkeypatch.setattr(
        "bybit_automation.infrastructure.windows_browser_finder.get_process_image_path",
        lambda _process_id: r"C:\Users\DeepD\AppData\Local\ms-playwright\chromium-1200\chrome-win64\chrome.exe",
    )

    assert finder._matches_window("Playwright Chromium", "Bybit", 1) is True
