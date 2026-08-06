from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderDetectionResult:
    """Результат чтения таблицы заказов без навигации по другим вкладкам."""

    found: bool
    url: str = ""
    row_count: int = 0
    rows_text: tuple[str, ...] = ()
    empty_marker: str = "No Records"

