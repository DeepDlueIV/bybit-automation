from __future__ import annotations

from dataclasses import dataclass

from bybit_automation.infrastructure.paths import AppPaths
from bybit_automation.infrastructure.portable_chrome_browser_driver import (
    PORTABLE_CHROME_VERSION,
)


@dataclass(frozen=True)
class RuntimeCheck:
    name: str
    ok: bool
    message: str


@dataclass(frozen=True)
class RuntimePreflightReport:
    paths: AppPaths
    checks: tuple[RuntimeCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def summary(self) -> str:
        status = "готово" if self.ok else "обнаружены проблемы"
        details = "; ".join(
            f"{check.name}={'ok' if check.ok else 'fail'}: {check.message}"
            for check in self.checks
        )
        return f"Проверка среды: {status}; {details}; лог={self.paths.log_file}"

    def check(self, name: str) -> RuntimeCheck:
        for item in self.checks:
            if item.name == name:
                return item
        raise KeyError(name)


def _check_data_directory(paths: AppPaths) -> RuntimeCheck:
    probe = paths.data_dir / ".write-test"
    try:
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
    except OSError as error:
        return RuntimeCheck(
            name="data_directory",
            ok=False,
            message=f"нет доступа на запись: {paths.data_dir}; ошибка={error}",
        )
    return RuntimeCheck(
        name="data_directory",
        ok=True,
        message=f"доступен для записи: {paths.data_dir}",
    )


def run_runtime_preflight(paths: AppPaths) -> RuntimePreflightReport:
    try:
        paths.prepare_runtime_layout()
        root_check = RuntimeCheck(
            name="runtime_root",
            ok=True,
            message=f"корень программы: {paths.root_dir}",
        )
        data_check = _check_data_directory(paths)
    except OSError as error:
        root_check = RuntimeCheck(
            name="runtime_root",
            ok=False,
            message=f"не удалось подготовить корень {paths.root_dir}; ошибка={error}",
        )
        data_check = RuntimeCheck(
            name="data_directory",
            ok=False,
            message=f"каталог данных недоступен: {paths.data_dir}",
        )

    browser_exists = paths.portable_chrome_executable.is_file()
    browser_check = RuntimeCheck(
        name="portable_chrome",
        ok=browser_exists,
        message=(
            f"файл найден; ожидаемая версия {PORTABLE_CHROME_VERSION}; "
            f"путь: {paths.portable_chrome_executable}"
            if browser_exists
            else (
                f"Portable Chrome {PORTABLE_CHROME_VERSION} не найден: "
                f"{paths.portable_chrome_executable}"
            )
        ),
    )
    sound_exists = paths.alarm_sound_file.is_file()
    sound_check = RuntimeCheck(
        name="alarm_sound",
        ok=sound_exists,
        message=(
            f"звуковой файл: {paths.alarm_sound_file}"
            if sound_exists
            else f"звуковой файл не найден: {paths.alarm_sound_file}"
        ),
    )
    return RuntimePreflightReport(
        paths=paths,
        checks=(root_check, data_check, browser_check, sound_check),
    )
