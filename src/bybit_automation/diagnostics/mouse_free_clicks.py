from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Iterable


WINDOW_TITLE_MARKERS = ("Bybit", "bybit", "ILYA BB")
PATTERN_NAMES = (
    "iface_invoke",
    "iface_selection_item",
    "iface_toggle",
    "iface_value",
    "iface_expand_collapse",
    "iface_legacy_iaccessible",
)


def Desktop(*args, **kwargs):
    from pywinauto import Desktop as PywinautoDesktop

    return PywinautoDesktop(*args, **kwargs)


def send_keys(*args, **kwargs) -> None:
    from pywinauto.keyboard import send_keys as pywinauto_send_keys

    pywinauto_send_keys(*args, **kwargs)


@dataclass(frozen=True)
class CandidateFinding:
    code_location: str
    current_mouse_click: str
    control_name: str
    control_type: str
    class_name: str
    patterns: list[str]
    evidence: str = ""


@dataclass(frozen=True)
class CandidateClassification:
    code_location: str
    current_mouse_click: str
    replacement_method: str
    status: str
    risk: str
    evidence: str


def available_patterns(control: object) -> list[str]:
    patterns: list[str] = []
    for pattern_name in PATTERN_NAMES:
        try:
            pattern = getattr(control, pattern_name)
        except Exception:
            continue
        if pattern is not None:
            patterns.append(pattern_name)
    return patterns


def classify_candidate(finding: CandidateFinding) -> CandidateClassification:
    method = _best_method(finding.patterns)
    if method:
        risk = "низкий" if method in {"iface_invoke", "iface_value"} else "средний"
        status = "кандидат найден"
    elif finding.control_type == "Image":
        risk = "высокий"
        status = "нужен parent/sibling candidate"
    else:
        risk = "средний"
        status = "нужен live-test"
    return CandidateClassification(
        code_location=finding.code_location,
        current_mouse_click=finding.current_mouse_click,
        replacement_method=method,
        status=status,
        risk=risk,
        evidence=finding.evidence,
    )


def _best_method(patterns: Iterable[str]) -> str:
    ordered = (
        "iface_invoke",
        "iface_value",
        "iface_selection_item",
        "iface_toggle",
        "iface_expand_collapse",
        "iface_legacy_iaccessible",
    )
    pattern_set = set(patterns)
    for pattern in ordered:
        if pattern in pattern_set:
            return pattern
    return ""


def _text(control: object) -> str:
    try:
        return control.window_text().strip()
    except Exception:
        return ""


def _control_type(control: object) -> str:
    try:
        return getattr(getattr(control, "element_info", None), "control_type", "")
    except Exception:
        return ""


def _class_name(control: object) -> str:
    try:
        return getattr(getattr(control, "element_info", None), "class_name", "")
    except Exception:
        return ""


def _rect(control: object) -> str:
    try:
        return str(getattr(getattr(control, "element_info", None), "rectangle", ""))
    except Exception:
        return ""


def _find_window(window_title: str | None = None):
    if window_title:
        return Desktop(backend="uia").window(title=window_title)
    candidates = []
    for window in Desktop(backend="uia").windows():
        title = _text(window)
        if title and any(marker in title for marker in WINDOW_TITLE_MARKERS):
            candidates.append(window)
    if not candidates:
        raise RuntimeError("Не найдено окно браузера Bybit.")
    return candidates[0]


def _descendants(window) -> list[object]:
    try:
        return list(window.descendants())
    except Exception:
        return []


def _find_address_bar(window) -> object | None:
    for control in _descendants(window):
        if _control_type(control) == "Edit" and "bybit.com/" in _text(control):
            return control
    return None


def _find_place_button(window) -> object | None:
    for control in _descendants(window):
        if _control_type(control) == "Button" and "Разместить" in _text(control):
            return control
    return None


def _find_current_ad_row(window) -> object | None:
    for control in _descendants(window):
        if _control_type(control) == "DataItem" and _text(control).isdigit() and len(_text(control)) >= 10:
            try:
                return control.parent()
            except Exception:
                return None
    return None


def _row_action_images(row: object) -> list[object]:
    images = []
    try:
        controls = row.descendants()
    except Exception:
        return images
    for control in controls:
        if _control_type(control) == "Image":
            images.append(control)
    return images


def _parent_chain(control: object, depth: int = 3) -> list[object]:
    chain = []
    current = control
    for _ in range(depth):
        try:
            current = current.parent()
        except Exception:
            break
        chain.append(current)
    return chain


def _finding_for_control(
    *,
    code_location: str,
    current_mouse_click: str,
    control: object,
    evidence: str,
) -> CandidateFinding:
    return CandidateFinding(
        code_location=code_location,
        current_mouse_click=current_mouse_click,
        control_name=_text(control),
        control_type=_control_type(control),
        class_name=_class_name(control),
        patterns=available_patterns(control),
        evidence=evidence,
    )


def collect_findings(window) -> list[CandidateFinding]:
    findings: list[CandidateFinding] = []

    address_bar = _find_address_bar(window)
    if address_bar is not None:
        findings.append(
            _finding_for_control(
                code_location="existing_browser_window_driver.py:1049",
                current_mouse_click="address_bar.click_input()",
                control=address_bar,
                evidence=f"address bar rect={_rect(address_bar)}",
            )
        )

    place_button = _find_place_button(window)
    if place_button is not None:
        findings.append(
            _finding_for_control(
                code_location="existing_browser_window_driver.py:991",
                current_mouse_click="open_button.click_input()",
                control=place_button,
                evidence=f"button rect={_rect(place_button)}",
            )
        )

    row = _find_current_ad_row(window)
    if row is not None:
        images = _row_action_images(row)
        if images:
            delete_image = images[-1]
            findings.append(
                _finding_for_control(
                    code_location="existing_browser_window_driver.py:780",
                    current_mouse_click="delete_icon.click_input()",
                    control=delete_image,
                    evidence=f"delete image class={_class_name(delete_image)!r} rect={_rect(delete_image)}",
                )
            )
            for index, parent in enumerate(_parent_chain(delete_image, depth=3), start=1):
                findings.append(
                    _finding_for_control(
                        code_location="existing_browser_window_driver.py:780 parent candidate",
                        current_mouse_click=f"delete_icon.parent({index}) mouse-free candidate",
                        control=parent,
                        evidence=f"parent_level={index} rect={_rect(parent)}",
                    )
                )
        findings.append(
            _finding_for_control(
                code_location="existing_browser_window_driver.py:792",
                current_mouse_click="row_data_item.click_input(button='right')",
                control=row,
                evidence=f"row rect={_rect(row)}",
            )
        )

    return findings


def _popup_markers(window) -> list[str]:
    markers = []
    for control in _descendants(window):
        text = _text(control)
        if text and any(part in text for part in ("Стандартная P2P", "Блочная торговля", "Удалить", "Подтверд")):
            markers.append(text)
    return markers


def _safe_invoke_and_close(window_title: str | None, label: str, control: object, expected_marker: str) -> str:
    try:
        control.iface_invoke.Invoke()
    except Exception as error:
        return f"{label}: invoke failed: {type(error).__name__}: {error}"

    time.sleep(0.8)
    window = _find_window(window_title)
    markers = _popup_markers(window)
    opened = any(expected_marker in marker for marker in markers)
    send_keys("{ESC}")
    time.sleep(0.4)
    window = _find_window(window_title)
    markers_after_close = _popup_markers(window)
    closed = not any(expected_marker in marker for marker in markers_after_close)
    return f"{label}: opened={opened}; closed={closed}; markers={markers[:6]}"


def run_safe_action_checks(window_title: str | None, window) -> list[str]:
    results: list[str] = []

    place_button = _find_place_button(window)
    if place_button is not None and "iface_invoke" in available_patterns(place_button):
        results.append(_safe_invoke_and_close(window_title, "Разместить объявления", place_button, "Стандартная P2P"))
    else:
        results.append("Разместить объявления: skipped, iface_invoke candidate not found")

    window = _find_window(window_title)
    row = _find_current_ad_row(window)
    if row is None:
        results.append("Удаление объявления: skipped, ad row not found")
        return results

    images = _row_action_images(row)
    if not images:
        results.append("Удаление объявления: skipped, row images not found")
        return results

    delete_image = images[-1]
    parent_candidates = [candidate for candidate in _parent_chain(delete_image, depth=3) if "iface_invoke" in available_patterns(candidate)]
    if not parent_candidates:
        results.append("Удаление объявления: skipped, invokable parent candidate not found")
        return results

    results.append(_safe_invoke_and_close(window_title, "Удаление через parent iface_invoke", parent_candidates[0], "Подтверд"))
    return results


def format_report(findings: list[CandidateFinding], safe_action_results: list[str]) -> str:
    lines = ["# Mouse-free click diagnostics", ""]
    lines.append("| code | physical click | control | patterns | replacement | status | risk | evidence |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for finding in findings:
        classification = classify_candidate(finding)
        control = f"{finding.control_type} {finding.control_name or finding.class_name}".strip()
        lines.append(
            "| "
            + " | ".join(
                [
                    finding.code_location,
                    finding.current_mouse_click,
                    control.replace("|", "/"),
                    ", ".join(finding.patterns) or "-",
                    classification.replacement_method or "-",
                    classification.status,
                    classification.risk,
                    finding.evidence.replace("|", "/"),
                ]
            )
            + " |"
        )
    if safe_action_results:
        lines.extend(["", "## Safe action checks", ""])
        lines.extend(f"- {result}" for result in safe_action_results)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Диагностика mouse-free альтернатив UIA-кликам.")
    parser.add_argument("--window-title", default=None)
    parser.add_argument("--safe-actions", action="store_true")
    args = parser.parse_args()

    window = _find_window(args.window_title)
    title = _text(window)
    print(f"Window: {title}")
    address_bar = _find_address_bar(window)
    if address_bar is not None:
        print(f"URL: {_text(address_bar)}")

    findings = collect_findings(window)
    safe_results = run_safe_action_checks(args.window_title, window) if args.safe_actions else []
    print(format_report(findings, safe_results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
