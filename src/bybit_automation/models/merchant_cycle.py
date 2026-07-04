from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdvertisementSnapshot:
    advertisement_id: str
    price: str
    side: str


@dataclass(frozen=True)
class MerchantSearchResult:
    found: bool
    page: int = 0
    position: int = 0
    matched_name: str = ""


@dataclass(frozen=True)
class MerchantCycleResult:
    success: bool
    stopped: bool
    attempts: int
    message: str
    advertisement_id: str = ""
    price: str = ""
    page: int = 0
    position: int = 0
