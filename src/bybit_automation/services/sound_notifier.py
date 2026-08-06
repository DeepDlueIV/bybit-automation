from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from threading import Thread


BeepFunc = Callable[[int, int], None]
SystemSoundFunc = Callable[[], None]
PlaybackCallback = Callable[[str], None]


def _running_under_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


class AccountFoundSoundNotifier:
    """Проигрывает уведомление о найденном и успешно записанном аккаунте."""

    fallback_sequence: tuple[tuple[int, int], ...] = (
        (880, 180),
        (1175, 180),
        (1568, 260),
        (1175, 180),
        (1568, 320),
    )

    def __init__(
        self,
        system_sound: SystemSoundFunc | None = None,
        beep: BeepFunc | None = None,
        *,
        async_play: bool = True,
        on_playback: PlaybackCallback | None = None,
    ) -> None:
        self._system_sound = system_sound or self._default_system_sound
        self._beep = beep or self._default_beep
        self._async_play = async_play
        self._on_playback = on_playback

    def notify(self) -> None:
        if self._async_play:
            Thread(target=self._play_notification, daemon=True).start()
            return
        self._play_notification()

    def _play_notification(self) -> None:
        try:
            self._system_sound()
        except Exception:
            self._emit_playback("fallback")
            for frequency, duration_ms in self.fallback_sequence:
                self._beep(frequency, duration_ms)
            return
        self._emit_playback("system")

    def _emit_playback(self, mode: str) -> None:
        if self._on_playback is not None:
            self._on_playback(mode)

    @staticmethod
    def _default_system_sound() -> None:
        if _running_under_pytest():
            return
        try:
            import winsound
        except ImportError as error:
            raise RuntimeError("winsound недоступен") from error
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

    @staticmethod
    def _default_beep(frequency: int, duration_ms: int) -> None:
        if _running_under_pytest():
            return
        try:
            import winsound
        except ImportError:
            return
        winsound.Beep(frequency, duration_ms)


class ErrorSoundNotifier:
    """Проигрывает низкий тревожный сигнал при ошибке цикла."""

    sequence: tuple[tuple[int, int], ...] = (
        (400, 200),
        (250, 200),
        (150, 400),
    )

    def __init__(self, beep: BeepFunc | None = None, *, async_play: bool = True) -> None:
        self._beep = beep or self._default_beep
        self._async_play = async_play

    def play(self) -> None:
        if self._async_play:
            Thread(target=self._play_sequence, daemon=True).start()
            return
        self._play_sequence()

    def _play_sequence(self) -> None:
        for frequency, duration_ms in self.sequence:
            self._beep(frequency, duration_ms)

    @staticmethod
    def _default_beep(frequency: int, duration_ms: int) -> None:
        if _running_under_pytest():
            return
        try:
            import winsound
        except ImportError:
            return
        winsound.Beep(frequency, duration_ms)


class LoopSoundNotifier:
    """Проигрывает WAV циклически до явной остановки."""

    def __init__(self, sound_path: Path) -> None:
        self._sound_path = sound_path

    def start(self) -> None:
        if _running_under_pytest():
            return
        import winsound
        winsound.PlaySound(str(self._sound_path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)

    def stop(self) -> None:
        if _running_under_pytest():
            return
        import winsound
        winsound.PlaySound(None, winsound.SND_PURGE)
