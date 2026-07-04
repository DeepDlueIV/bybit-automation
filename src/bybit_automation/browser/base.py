from __future__ import annotations

from typing import Protocol


class BrowserClient(Protocol):
    """Future pluggable browser client interface."""

    def connect(self) -> None:
        """Connect to a browser profile."""
