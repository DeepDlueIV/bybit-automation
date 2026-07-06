from __future__ import annotations

import pytest

from bybit_automation.infrastructure.playwright_browser_driver import PlaywrightBrowserDriver
from bybit_automation.models.automation_mode import AutomationMode
from bybit_automation.services.logging_service import AppLogger


def test_incogniton_cdp_mode_requires_endpoint(tmp_path) -> None:
    driver = PlaywrightBrowserDriver(
        logger=AppLogger(),
        mode=AutomationMode.INCOGNITON_PLAYWRIGHT_CDP,
        user_data_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
        cdp_endpoint="",
    )

    with pytest.raises(RuntimeError, match="BYBIT_PLAYWRIGHT_CDP_ENDPOINT"):
        driver.focus("Incogniton Playwright/CDP")

