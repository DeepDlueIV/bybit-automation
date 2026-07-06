from __future__ import annotations


class AutomationMode:
    INCOGNITON_UIA = "Incogniton UIA"
    INCOGNITON_PLAYWRIGHT_CDP = "Incogniton Playwright/CDP"
    PLAYWRIGHT_PROFILE = "Playwright profile"

    @classmethod
    def choices(cls) -> list[str]:
        return [
            cls.INCOGNITON_UIA,
            cls.INCOGNITON_PLAYWRIGHT_CDP,
            cls.PLAYWRIGHT_PROFILE,
        ]

