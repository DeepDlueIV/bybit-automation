from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlsplit, urlunsplit

from bybit_automation.infrastructure.paths import AppPaths
from bybit_automation.infrastructure.playwright_browser_driver import PlaywrightBrowserDriver
from bybit_automation.models.automation_mode import AutomationMode
from bybit_automation.services.logging_service import AppLogger


REQUIRED_CHROME_FLAGS = (
    "--remote-debugging-port",
    "--user-data-dir",
    "--remote-allow-origins=*",
    "--start-maximized",
    "--no-first-run",
    "--no-default-browser-check",
    "about:blank",
)


def _flag_is_present(command_line: str, flag: str) -> bool:
    if flag in {"--remote-debugging-port", "--user-data-dir"}:
        return f"{flag}=" in command_line
    return flag in command_line


def find_profile_process(processes: Sequence[dict[str, Any]], profile_dir: Path) -> dict[str, Any] | None:
    expected_profile = str(profile_dir.resolve()).casefold()
    for raw_process in processes:
        command_line = str(raw_process.get("CommandLine") or "")
        if expected_profile not in command_line.casefold():
            continue
        port_match = re.search(r"--remote-debugging-port=(\d+)", command_line)
        if port_match is None:
            continue
        return {
            "found": True,
            "pid": int(raw_process.get("ProcessId") or 0),
            "executable": str(raw_process.get("ExecutablePath") or ""),
            "command_line": command_line,
            "cdp_port": int(port_match.group(1)),
            "profile_matches": True,
            "required_flags": {
                flag: _flag_is_present(command_line, flag)
                for flag in REQUIRED_CHROME_FLAGS
            },
        }
    return None


def read_chrome_processes() -> list[dict[str, Any]]:
    script = (
        "$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
        "Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Не удалось прочитать процессы Chrome: {completed.stderr.strip()}")
    payload = completed.stdout.strip()
    if not payload or payload == "null":
        return []
    decoded = json.loads(payload)
    return decoded if isinstance(decoded, list) else [decoded]


def _read_json_url(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _safe_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"}:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return value.split("?", 1)[0].split("#", 1)[0]


def read_cdp_snapshot(endpoint: str) -> dict[str, Any]:
    try:
        version = _read_json_url(f"{endpoint}/json/version")
        targets = _read_json_url(f"{endpoint}/json/list")
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
        return {
            "reachable": False,
            "endpoint": endpoint,
            "error": f"{type(error).__name__}: {error}",
        }

    target_list = targets if isinstance(targets, list) else []
    target_types = Counter(str(target.get("type") or "unknown") for target in target_list)
    return {
        "reachable": True,
        "endpoint": endpoint,
        "browser": str(version.get("Browser") or ""),
        "protocol_version": str(version.get("Protocol-Version") or ""),
        "user_agent": str(version.get("User-Agent") or ""),
        "target_count": len(target_list),
        "target_types": dict(sorted(target_types.items())),
        "targets": [
            {
                "id": str(target.get("id") or ""),
                "type": str(target.get("type") or ""),
                "title": str(target.get("title") or ""),
                "url": _safe_url(str(target.get("url") or "")),
            }
            for target in target_list
        ],
    }


def probe_automation(driver: Any) -> dict[str, Any]:
    try:
        discovery = driver.discover_profile()
        context = getattr(driver, "_context", None)
        pages = list(context.pages) if context is not None else []
        page_snapshots: list[dict[str, Any]] = []
        successful_dom_reads = 0
        for page in pages:
            try:
                page_snapshots.append(
                    {
                        "url": _safe_url(str(page.url)),
                        "title": str(page.title()),
                        "ready_state": str(page.evaluate("document.readyState")),
                        "body_length": int(page.evaluate("document.body ? document.body.innerText.length : 0")),
                        "window_size": page.evaluate("({width: window.innerWidth, height: window.innerHeight})"),
                        "viewport_size": page.viewport_size,
                    }
                )
                successful_dom_reads += 1
            except Exception as error:
                page_snapshots.append(
                    {
                        "url": _safe_url(str(getattr(page, "url", ""))),
                        "read_error": f"{type(error).__name__}: {error}",
                    }
                )

        browser = getattr(driver, "_browser", None)
        return {
            "connected": bool(getattr(discovery, "connected", False) and context is not None),
            "discovery_connected": bool(getattr(discovery, "connected", False)),
            "browser_name": str(getattr(discovery, "browser_name", "")),
            "window_title": str(getattr(discovery, "window_title", "")),
            "browser_version": str(getattr(browser, "version", "")),
            "tab_count": len(getattr(discovery, "tabs", [])),
            "page_count": len(pages),
            "dom_read_ok": successful_dom_reads > 0,
            "pages": page_snapshots,
        }
    except Exception as error:
        return {
            "connected": False,
            "discovery_connected": False,
            "dom_read_ok": False,
            "page_count": 0,
            "pages": [],
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        disconnect = getattr(driver, "_drop_playwright_connection", None)
        if callable(disconnect):
            disconnect()


def assemble_baseline(
    *,
    profile_dir: Path,
    process: dict[str, Any],
    cdp: dict[str, Any],
    automation: dict[str, Any],
    python_version: str,
    playwright_version: str,
    captured_at: str,
) -> dict[str, Any]:
    required_flags = process.get("required_flags") or {}
    checks = {
        "process_found": bool(process.get("found")),
        "profile_matches": bool(process.get("profile_matches")),
        "required_flags_present": all(bool(required_flags.get(flag)) for flag in REQUIRED_CHROME_FLAGS),
        "cdp_reachable": bool(cdp.get("reachable")),
        "playwright_connected": bool(
            automation.get("connected") and automation.get("discovery_connected")
        ),
        "automation_dom_read": bool(automation.get("dom_read_ok")),
        "browser_survived_probe": bool(process.get("alive_after_probe")),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": 1,
        "captured_at": captured_at,
        "ok": not failures,
        "failures": failures,
        "benchmark": {
            "name": "System Chrome browser + CDP + Playwright automation chain",
            "browser": "System Chrome",
            "automation_mode": AutomationMode.SYSTEM_CHROME_EXTENSIONS_PROFILE,
            "connection": "external Chrome process -> Playwright connect_over_cdp",
            "read_only": True,
            "extension_is_part_of_benchmark": False,
        },
        "expected": {
            "profile_dir": str(profile_dir.resolve()),
            "required_chrome_flags": list(REQUIRED_CHROME_FLAGS),
        },
        "runtime": {
            "python_version": python_version,
            "playwright_version": playwright_version,
        },
        "process": process,
        "cdp": cdp,
        "automation": automation,
        "checks": checks,
    }


def capture_baseline(
    app_paths: AppPaths,
    *,
    process_reader: Callable[[], list[dict[str, Any]]] = read_chrome_processes,
) -> dict[str, Any]:
    profile_dir = app_paths.system_chrome_extensions_profile_dir
    process = find_profile_process(process_reader(), profile_dir)
    if process is None:
        process = {
            "found": False,
            "pid": None,
            "executable": "",
            "command_line": "",
            "cdp_port": None,
            "profile_matches": False,
            "alive_after_probe": False,
            "required_flags": {flag: False for flag in REQUIRED_CHROME_FLAGS},
        }
        cdp = {"reachable": False, "endpoint": "", "error": "Профильный Chrome-процесс не найден"}
        automation = {
            "connected": False,
            "discovery_connected": False,
            "dom_read_ok": False,
            "page_count": 0,
            "pages": [],
            "error": "CDP-подключение не выполнялось без профильного Chrome-процесса",
        }
    else:
        endpoint = f"http://127.0.0.1:{process['cdp_port']}"
        cdp = read_cdp_snapshot(endpoint)
        driver = PlaywrightBrowserDriver(
            logger=AppLogger(),
            mode=AutomationMode.SYSTEM_CHROME_EXTENSIONS_PROFILE,
            user_data_dir=profile_dir,
            artifacts_dir=app_paths.playwright_artifacts_dir,
        )
        automation = probe_automation(driver) if cdp.get("reachable") else {
            "connected": False,
            "discovery_connected": False,
            "dom_read_ok": False,
            "page_count": 0,
            "pages": [],
            "error": "Playwright-подключение не выполнялось: CDP недоступен",
        }
        process_after_probe = find_profile_process(process_reader(), profile_dir)
        process["alive_after_probe"] = bool(
            process_after_probe is not None
            and process_after_probe.get("pid") == process.get("pid")
        )

    try:
        playwright_version = importlib.metadata.version("playwright")
    except importlib.metadata.PackageNotFoundError:
        playwright_version = "not-installed"
    return assemble_baseline(
        profile_dir=profile_dir,
        process=process,
        cdp=cdp,
        automation=automation,
        python_version=sys.version.split()[0],
        playwright_version=playwright_version,
        captured_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )


def write_baseline(output: Path, baseline: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _wait_for_profile_process(profile_dir: Path, wait_seconds: float) -> None:
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while time.monotonic() < deadline:
        if find_profile_process(read_chrome_processes(), profile_dir) is not None:
            return
        time.sleep(0.5)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only эталон связки System Chrome + CDP + Playwright")
    parser.add_argument("--output", type=Path, help="Путь к JSON; по умолчанию data/system-chrome-baseline/")
    parser.add_argument("--wait-seconds", type=float, default=0.0, help="Сколько ждать уже запускаемый профильный Chrome")
    args = parser.parse_args(argv)

    app_paths = AppPaths.from_cwd()
    _wait_for_profile_process(app_paths.system_chrome_extensions_profile_dir, args.wait_seconds)
    baseline = capture_baseline(app_paths)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.output or app_paths.data_dir / "system-chrome-baseline" / f"{timestamp}.json"
    write_baseline(output, baseline)
    if args.output is None:
        write_baseline(output.parent / "latest.json", baseline)
    print(json.dumps({"ok": baseline["ok"], "failures": baseline["failures"], "output": str(output)}, ensure_ascii=False))
    return 0 if baseline["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
