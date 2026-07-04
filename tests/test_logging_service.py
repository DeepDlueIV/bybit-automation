from __future__ import annotations

from pathlib import Path

from bybit_automation.services.logging_service import AppLogger


def test_app_logger_writes_messages_to_log_file_with_session_header(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"

    logger = AppLogger(log_file=log_file)
    logger.info("Первое сообщение")
    logger.info("Второе сообщение")

    content = log_file.read_text(encoding="utf-8")

    assert "Новая сессия:" in content
    assert "Первое сообщение" in content
    assert "Второе сообщение" in content


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
