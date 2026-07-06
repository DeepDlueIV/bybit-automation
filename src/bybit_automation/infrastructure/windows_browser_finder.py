from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from bybit_automation.infrastructure.existing_browser_window_driver import get_process_image_path


def Desktop(*args, **kwargs):
    from pywinauto import Desktop as PywinautoDesktop

    return PywinautoDesktop(*args, **kwargs)


@dataclass
class WindowsBrowserWindow:
    title: str
    element: object

    def child_titles(self) -> Iterable[str]:
        try:
            children = self.element.descendants()
        except Exception:
            return []
        titles: list[str] = []
        for child in children:
            try:
                texts = child.window_text()
                control_type = getattr(getattr(child, "element_info", None), "control_type", "")
            except Exception:
                continue
            if not texts:
                continue
            text = texts.strip()
            if not text:
                continue
            if control_type != "TabItem":
                continue
            if len(text) > 80:
                continue
            if text.lower() in {"system", "minimize", "restore", "close"}:
                continue
            titles.append(text)
        seen: set[str] = set()
        unique_titles: list[str] = []
        for title in titles:
            if title not in seen:
                seen.add(title)
                unique_titles.append(title)
        return unique_titles


class WindowsBrowserFinder:
    def find_windows(self, browser_name: str) -> list[WindowsBrowserWindow]:
        windows: list[WindowsBrowserWindow] = []
        for element in Desktop(backend="uia").windows():
            try:
                title = element.window_text()
                process_id = element.process_id()
            except Exception:
                continue
            if not title:
                continue
            if self._matches_window(browser_name, title, process_id):
                windows.append(WindowsBrowserWindow(title=title, element=element))
        return windows

    def _matches_window(self, browser_name: str, title: str, process_id: int) -> bool:
        image_path = get_process_image_path(process_id).lower()
        title_lower = title.lower()

        if browser_name == "Incogniton":
            return "\\incogniton\\browser\\" in image_path and image_path.endswith("chrome.exe")
        if browser_name == "System Chrome":
            return (
                image_path.endswith("\\chrome.exe")
                and "\\incogniton\\browser\\" not in image_path
                and "\\ms-playwright\\" not in image_path
            )
        if browser_name == "Playwright Chromium":
            return "\\ms-playwright\\" in image_path and (
                image_path.endswith("\\chrome.exe") or image_path.endswith("\\chromium.exe")
            )
        return browser_name.lower() in title_lower
