from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentMethodState:
    bank_transfer: bool
    mobile_top_up: bool
    cash_deposit: bool

