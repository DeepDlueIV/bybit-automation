from __future__ import annotations

from bybit_automation.services.sound_notifier import AccountFoundSoundNotifier, ErrorSoundNotifier


def test_account_found_sound_notifier_plays_fallback_sequence_when_system_sound_fails() -> None:
    played: list[tuple[int, int]] = []

    def failing_system_sound() -> None:
        raise RuntimeError("system sound unavailable")

    notifier = AccountFoundSoundNotifier(
        system_sound=failing_system_sound,
        beep=lambda frequency, duration: played.append((frequency, duration)),
        async_play=False,
    )

    notifier.notify()

    assert played == list(notifier.fallback_sequence)


def test_account_found_sound_notifier_uses_system_sound_before_fallback() -> None:
    events: list[str] = []

    notifier = AccountFoundSoundNotifier(
        system_sound=lambda: events.append("system"),
        beep=lambda _frequency, _duration: events.append("beep"),
        async_play=False,
    )

    notifier.notify()

    assert events == ["system"]


def test_account_found_sound_notifier_fallback_sequence_is_shorter_than_three_seconds() -> None:
    notifier = AccountFoundSoundNotifier(system_sound=lambda: None, beep=lambda _frequency, _duration: None, async_play=False)

    total_ms = sum(duration for _, duration in notifier.fallback_sequence)

    assert total_ms <= 3000


def test_error_sound_notifier_plays_sequence_on_any_call() -> None:
    played: list[tuple[int, int]] = []
    notifier = ErrorSoundNotifier(beep=lambda frequency, duration: played.append((frequency, duration)), async_play=False)

    notifier.play()
    notifier.play()

    assert len(played) == len(notifier.sequence) * 2


def test_error_sound_notifier_sequence_is_shorter_than_two_seconds() -> None:
    notifier = ErrorSoundNotifier(beep=lambda _frequency, _duration: None, async_play=False)

    total_ms = sum(duration for _, duration in notifier.sequence)

    assert total_ms <= 2000
