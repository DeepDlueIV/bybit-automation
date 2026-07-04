from __future__ import annotations

from dataclasses import dataclass

from bybit_automation.services.browser_discovery_service import BrowserDiscoveryService


@dataclass
class FakeWindow:
    title: str
    titles: list[str]

    def child_titles(self):
        return self.titles


class FakeFinder:
    def __init__(self, windows):
        self._windows = windows

    def find_windows(self, browser_name: str):
        return self._windows.get(browser_name, [])


def test_discover_returns_connected_result_with_tabs():
    finder = FakeFinder(
        {
            "Chrome": [
                FakeWindow(
                    title="Chrome - Bybit",
                    titles=["Bybit P2P", "Another Tab"],
                )
            ]
        }
    )
    service = BrowserDiscoveryService(finder=finder)

    result = service.discover("Chrome")

    assert result.connected is True
    assert result.window_title == "Chrome - Bybit"
    assert [tab.title for tab in result.tabs] == ["Bybit P2P", "Another Tab"]


def test_discover_marks_ads_and_sell_tabs_separately():
    finder = FakeFinder(
        {
            "Chrome": [
                FakeWindow(
                    title="Chrome - Bybit",
                    titles=[
                        "Продать USDT за RUB через криптотрейдинг на Bybit P2P",
                        "Мои объявления | Bybit",
                        "Another Tab",
                    ],
                )
            ]
        }
    )
    service = BrowserDiscoveryService(finder=finder)

    result = service.discover("Chrome")

    assert result.ads_tab_title == "Мои объявления | Bybit"
    assert result.sell_tab_title == "Продать USDT за RUB через криптотрейдинг на Bybit P2P"


def test_discover_returns_empty_result_when_browser_missing():
    service = BrowserDiscoveryService(finder=FakeFinder({}))

    result = service.discover("Chrome")

    assert result.connected is False
    assert result.window_title == ""
    assert result.tabs == []
