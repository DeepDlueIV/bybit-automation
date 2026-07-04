from __future__ import annotations

from pathlib import Path

import bybit_automation.services.logging_service as logging_service
from bybit_automation.services.logging_service import AppLogger


def test_app_logger_prefixes_messages_with_timestamp_and_delta(monkeypatch, tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    moments = iter(
        [
            logging_service.datetime(2026, 7, 4, 18, 42, 11, 235000),
            logging_service.datetime(2026, 7, 4, 18, 42, 12, 1000),
            logging_service.datetime(2026, 7, 4, 18, 42, 12, 201000),
        ]
    )

    class FakeDateTime(logging_service.datetime):
        @classmethod
        def now(cls):
            return next(moments)

    monkeypatch.setattr(logging_service, "datetime", FakeDateTime)
    messages: list[str] = []
    logger = AppLogger(log_file=log_file)
    logger.subscribe(messages.append)

    logger.info("Первое сообщение")
    logger.info("Второе сообщение")

    assert messages == [
        "2026-07-04 18:42:12.001 | +0.000s | Первое сообщение",
        "2026-07-04 18:42:12.201 | +0.200s | Второе сообщение",
    ]
    content = log_file.read_text(encoding="utf-8")
    assert "2026-07-04 18:42:12.001 | +0.000s | Первое сообщение" in content
    assert "2026-07-04 18:42:12.201 | +0.200s | Второе сообщение" in content


def test_app_logger_writes_messages_to_log_file_with_session_header(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"

    logger = AppLogger(log_file=log_file)
    logger.info("Первое сообщение")
    logger.info("Второе сообщение")

    content = log_file.read_text(encoding="utf-8")

    assert "Новая сессия:" in content
    assert "Первое сообщение" in content
    assert "Второе сообщение" in content
    assert " | +0.000s | " in content


def test_app_logger_appends_new_session_instead_of_overwriting_log_file(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"

    first_logger = AppLogger(log_file=log_file)
    first_logger.info("Сообщение 1")

    second_logger = AppLogger(log_file=log_file)
    second_logger.info("Сообщение 2")

    content = log_file.read_text(encoding="utf-8")

    assert content.count("Новая сессия:") == 2
    assert "Сообщение 1" in content
    assert "Сообщение 2" in content
