from __future__ import annotations


class AutomationMode:
    INCOGNITON_UIA = "Incogniton UIA"
    INCOGNITON_PLAYWRIGHT_CDP = "Incogniton Playwright/CDP"
    PLAYWRIGHT_PROFILE = "Playwright profile"
    PLAYWRIGHT_CHROMIUM_EXTENSIONS = "Playwright Chromium + extensions"
    SYSTEM_CHROME_EXTENSIONS_PROFILE = "System Chrome extensions profile"
    SYSTEM_CHROME_EXTENSIONS_RECOVERY = "System Chrome extensions profile (restart recovery)"
    PORTABLE_CHROME = "Portable Chrome 150"

    @classmethod
    def choices(cls) -> list[str]:
        return [
            cls.INCOGNITON_UIA,
            cls.INCOGNITON_PLAYWRIGHT_CDP,
            cls.PLAYWRIGHT_PROFILE,
            cls.PLAYWRIGHT_CHROMIUM_EXTENSIONS,
            cls.SYSTEM_CHROME_EXTENSIONS_PROFILE,
            cls.SYSTEM_CHROME_EXTENSIONS_RECOVERY,
            cls.PORTABLE_CHROME,
        ]

