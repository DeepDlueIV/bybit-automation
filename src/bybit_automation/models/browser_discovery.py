from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BrowserTabInfo:
    title: str
    role: str = "other"


@dataclass(frozen=True)
class BrowserDiscoveryResult:
    browser_name: str
    window_title: str
    tabs: list[BrowserTabInfo] = field(default_factory=list)
    ads_tab_title: str = ""
    sell_tab_title: str = ""
    connected: bool = False
