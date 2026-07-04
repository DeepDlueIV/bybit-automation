from __future__ import annotations

from typing import Protocol


class AutomationEngine(Protocol):
    """Future automation engine interface."""

    def run(self) -> None:
        """Run an automation job."""
