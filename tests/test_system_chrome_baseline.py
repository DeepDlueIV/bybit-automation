from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from bybit_automation.diagnostics.system_chrome_baseline import (
    REQUIRED_CHROME_FLAGS,
    assemble_baseline,
    find_profile_process,
    probe_automation,
    write_baseline,
)


def test_find_profile_process_requires_matching_profile_and_cdp_port(tmp_path: Path) -> None:
    profile_dir = tmp_path / "system-chrome-extensions-profile"
    processes = [
        {
            "ProcessId": 10,
            "ExecutablePath": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "CommandLine": r'chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\other-profile"',
        },
        {
            "ProcessId": 20,
            "ExecutablePath": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "CommandLine": (
                f'chrome.exe --remote-debugging-port=54321 "--user-data-dir={profile_dir}" '
                "--remote-allow-origins=* --start-maximized --no-first-run "
                "--no-default-browser-check about:blank"
            ),
        },
    ]

    process = find_profile_process(processes, profile_dir)

    assert process is not None
    assert process["pid"] == 20
    assert process["cdp_port"] == 54321
    assert process["profile_matches"] is True
    assert process["required_flags"] == {flag: True for flag in REQUIRED_CHROME_FLAGS}


def test_assemble_baseline_requires_complete_working_chain(tmp_path: Path) -> None:
    process = {
        "found": True,
        "pid": 20,
        "executable": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "command_line": "chrome.exe",
        "cdp_port": 54321,
        "profile_matches": True,
        "alive_after_probe": True,
        "required_flags": {flag: True for flag in REQUIRED_CHROME_FLAGS},
    }
    cdp = {"reachable": True, "browser": "Chrome/151.0.0.0", "target_count": 2}
    automation = {
        "connected": True,
        "discovery_connected": True,
        "dom_read_ok": True,
        "page_count": 2,
        "pages": [],
    }

    baseline = assemble_baseline(
        profile_dir=tmp_path,
        process=process,
        cdp=cdp,
        automation=automation,
        python_version="3.14.3",
        playwright_version="1.61.0",
        captured_at="2026-08-07T10:00:00+07:00",
    )

    assert baseline["ok"] is True
    assert baseline["failures"] == []
    assert baseline["benchmark"]["extension_is_part_of_benchmark"] is False
    assert baseline["checks"] == {
        "process_found": True,
        "profile_matches": True,
        "required_flags_present": True,
        "cdp_reachable": True,
        "playwright_connected": True,
        "automation_dom_read": True,
        "browser_survived_probe": True,
    }

    broken = assemble_baseline(
        profile_dir=tmp_path,
        process=process,
        cdp={"reachable": False},
        automation=automation,
        python_version="3.14.3",
        playwright_version="1.61.0",
        captured_at="2026-08-07T10:00:00+07:00",
    )

    assert broken["ok"] is False
    assert broken["failures"] == ["cdp_reachable"]


def test_probe_automation_reads_dom_and_disconnects_without_closing_browser() -> None:
    class FakePage:
        url = "https://www.bybit.com/ru-RU/p2p/sell/USDT/RUB"
        viewport_size = {"width": 1440, "height": 900}

        def title(self) -> str:
            return "Bybit"

        def evaluate(self, expression: str):
            values = {
                "document.readyState": "complete",
                "document.body ? document.body.innerText.length : 0": 1234,
                "({width: window.innerWidth, height: window.innerHeight})": {"width": 1440, "height": 900},
            }
            return values[expression]

    class FakeDriver:
        def __init__(self) -> None:
            self._context = SimpleNamespace(pages=[FakePage()])
            self.disconnected = False

        def discover_profile(self):
            return SimpleNamespace(
                connected=True,
                browser_name="System Chrome",
                window_title="System Chrome extensions profile",
                tabs=[SimpleNamespace(title="Bybit", role="sell")],
            )

        def _drop_playwright_connection(self) -> None:
            self.disconnected = True

        def close(self) -> None:
            raise AssertionError("Сборщик эталона не должен закрывать браузер")

    driver = FakeDriver()

    result = probe_automation(driver)

    assert result["connected"] is True
    assert result["dom_read_ok"] is True
    assert result["page_count"] == 1
    assert result["pages"][0]["ready_state"] == "complete"
    assert result["pages"][0]["body_length"] == 1234
    assert driver.disconnected is True


def test_write_baseline_creates_machine_readable_utf8_json(tmp_path: Path) -> None:
    output = tmp_path / "baseline.json"
    baseline = {"schema_version": 1, "ok": True, "message": "рабочая связка"}

    write_baseline(output, baseline)

    assert json.loads(output.read_text(encoding="utf-8")) == baseline
    assert output.read_bytes().startswith(b"{")
