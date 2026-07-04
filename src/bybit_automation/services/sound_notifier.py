from __future__ import annotations

from collections.abc import Callable
from threading import Thread


BeepFunc = Callable[[int, int], None]


class TopPositionSoundNotifier:
    """Проигрывает короткий нестандартный сигнал, когда аккаунт найден в топ-10."""

    sequence: tuple[tuple[int, int], ...] = (
        (880, 180),
        (1175, 180),
        (1568, 260),
        (1175, 180),
        (1568, 320),
    )

    def __init__(self, beep: BeepFunc | None = None, *, async_play: bool = True) -> None:
        self._beep = beep or self._default_beep
        self._async_play = async_play

    def notify_if_top_position(self, position: int) -> None:
        if not 1 <= position <= 10:
            return
        if self._async_play:
            Thread(target=self._play_sequence, daemon=True).start()
            return
        self._play_sequence()

    def _play_sequence(self) -> None:
        for frequency, duration_ms in self.sequence:
            self._beep(frequency, duration_ms)

    @staticmethod
    def _default_beep(frequency: int, duration_ms: int) -> None:
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
        try:
            import winsound
        except ImportError:
            return
        winsound.Beep(frequency, duration_ms)
