from __future__ import annotations

from bybit_automation.diagnostics.mouse_free_clicks import (
    CandidateFinding,
    available_patterns,
    classify_candidate,
)


class FakePattern:
    pass


class FakeControl:
    def __init__(self, *, invoke: bool = False, value: bool = False, toggle: bool = False) -> None:
        self._invoke = invoke
        self._value = value
        self._toggle = toggle

    @property
    def iface_invoke(self):
        if not self._invoke:
            raise RuntimeError("no invoke")
        return FakePattern()

    @property
    def iface_value(self):
        if not self._value:
            raise RuntimeError("no value")
        return FakePattern()

    @property
    def iface_toggle(self):
        if not self._toggle:
            raise RuntimeError("no toggle")
        return FakePattern()


def test_available_patterns_reports_only_supported_uia_patterns() -> None:
    control = FakeControl(invoke=True, value=True)

    assert available_patterns(control) == ["iface_invoke", "iface_value"]


def test_classify_candidate_marks_invoke_as_mouse_free_replacement() -> None:
    finding = CandidateFinding(
        code_location="driver.py:991",
        current_mouse_click="open_button.click_input()",
        control_name="Разместить объявления",
        control_type="Button",
        class_name="moly-btn",
        patterns=["iface_invoke"],
    )

    result = classify_candidate(finding)

    assert result.replacement_method == "iface_invoke"
    assert result.status == "кандидат найден"
    assert result.risk == "низкий"


def test_classify_candidate_marks_missing_patterns_as_needs_deep_live_test() -> None:
    finding = CandidateFinding(
        code_location="driver.py:780",
        current_mouse_click="delete_icon.click_input()",
        control_name="",
        control_type="Image",
        class_name="coin_removed_icon_svg__icon",
        patterns=[],
    )

    result = classify_candidate(finding)

    assert result.replacement_method == ""
    assert result.status == "нужен parent/sibling candidate"
    assert result.risk == "высокий"
