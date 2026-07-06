from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from bybit_automation.models.automation_mode import AutomationMode
from bybit_automation.models.browser_discovery import BrowserDiscoveryResult


@dataclass
class BrowserStatus:
    browser_name: str = "Incogniton"
    automation_mode: str = AutomationMode.INCOGNITON_UIA
    ads_tab_status: str = "Не подключено"
    sell_tab_status: str = "Не подключено"
    connection_status: str = "Не подключено"
    window_title: str = ""
    tabs_summary: str = ""
    ads_tab_title: str = ""
    sell_tab_title: str = ""

    def __post_init__(self) -> None:
        legacy_browser_names = {
            "Chrome": "System Chrome",
            "Chromium": "Playwright Chromium",
        }
        self.browser_name = legacy_browser_names.get(self.browser_name, self.browser_name)


@dataclass
class AdvertisementSettings:
    trade_side: str = "Покупка"
    fixed_price: str = "80"
    payment_time: str = "30 минут"
    total_amount: str = "20000"
    minimum_transaction: str = "4000"
    maximum_transaction: str = "3500000"
    phone_linked: bool = False
    email_linked: bool = False
    notes: str = ""
    payment_cash_deposit: bool = False
    payment_mobile_top_up: bool = False
    payment_bank_transfer: bool = False
    security_password: str = "Salam1337$"


@dataclass
class SearchSettings:
    account_name: str = ""
    depth: str = "4"
    current_page: str = ""
    current_position: str = ""
    search_status: str = ""


@dataclass
class LastResult:
    price: str = ""
    advertisement_id: str = ""
    page: str = ""
    position: str = ""


@dataclass
class AppState:
    browser: BrowserStatus = field(default_factory=BrowserStatus)
    advertisement: AdvertisementSettings = field(default_factory=AdvertisementSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    last_result: LastResult = field(default_factory=LastResult)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AppState":
        return cls(
            browser=BrowserStatus(**payload.get("browser", {})),
            advertisement=AdvertisementSettings(**payload.get("advertisement", {})),
            search=SearchSettings(**payload.get("search", {})),
            last_result=LastResult(**payload.get("last_result", {})),
        )

    @classmethod
    def from_browser_discovery(cls, result: BrowserDiscoveryResult) -> "AppState":
        connected_label = "Подключено" if result.connected else "Не подключено"
        ads_label = "Подключено" if result.ads_tab_title else "Не найдено"
        sell_label = "Подключено" if result.sell_tab_title else "Не найдено"
        tabs_summary = "\n".join(tab.title for tab in result.tabs)
        return cls(
            browser=BrowserStatus(
                browser_name=result.browser_name,
                ads_tab_status=ads_label,
                sell_tab_status=sell_label,
                connection_status=connected_label,
                window_title=result.window_title,
                tabs_summary=tabs_summary,
                ads_tab_title=result.ads_tab_title,
                sell_tab_title=result.sell_tab_title,
            )
        )
