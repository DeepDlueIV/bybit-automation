from __future__ import annotations

from bybit_automation.services.sound_notifier import TopPositionSoundNotifier


def test_top_position_sound_notifier_alerts_only_for_positions_1_to_10() -> None:
    played: list[tuple[int, int]] = []
    notifier = TopPositionSoundNotifier(beep=lambda frequency, duration: played.append((frequency, duration)), async_play=False)

    notifier.notify_if_top_position(0)
    notifier.notify_if_top_position(1)
    notifier.notify_if_top_position(10)
    notifier.notify_if_top_position(11)

    assert len(played) == len(notifier.sequence) * 2


def test_top_position_sound_notifier_sequence_is_shorter_than_three_seconds() -> None:
    notifier = TopPositionSoundNotifier(beep=lambda _frequency, _duration: None, async_play=False)

    total_ms = sum(duration for _, duration in notifier.sequence)

    assert total_ms <= 3000
