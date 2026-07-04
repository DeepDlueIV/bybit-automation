from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from bybit_automation.models.browser_discovery import BrowserDiscoveryResult, BrowserTabInfo


class WindowInfo(Protocol):
    title: str

    def child_titles(self) -> Iterable[str]:
        ...


class WindowFinder(Protocol):
    def find_windows(self, browser_name: str) -> list[WindowInfo]:
        ...


@dataclass
class BrowserDiscoveryService:
    finder: WindowFinder

    def _classify_role(self, title: str) -> str:
        title_lower = title.lower()
        if "merchant-admin/ads" in title_lower or "мои объявления" in title_lower:
            return "ads"
        if "sell/usdt/rub" in title_lower or ("usdt" in title_lower and "rub" in title_lower and ("прод" in title_lower or "sell" in title_lower)):
            return "sell"
        return "other"

    def discover(self, browser_name: str) -> BrowserDiscoveryResult:
        windows = self.finder.find_windows(browser_name)
        if not windows:
            return BrowserDiscoveryResult(
                browser_name=browser_name,
                window_title="",
                tabs=[],
                ads_tab_title="",
                sell_tab_title="",
                connected=False,
            )

        window = windows[0]
        tabs = [
            BrowserTabInfo(title=title, role=self._classify_role(title))
            for title in window.child_titles()
            if title.strip()
        ]
        ads_tab_title = next((tab.title for tab in tabs if tab.role == "ads"), "")
        sell_tab_title = next((tab.title for tab in tabs if tab.role == "sell"), "")
        return BrowserDiscoveryResult(
            browser_name=browser_name,
            window_title=window.title,
            tabs=tabs,
            ads_tab_title=ads_tab_title,
            sell_tab_title=sell_tab_title,
            connected=True,
        )
