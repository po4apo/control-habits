"""Тесты диалога баг-репорта и отправки в GitHub."""

from unittest.mock import MagicMock, patch

import pytest

from control_habits.bug_report.service import (
    BugReportPayload,
    create_github_issue,
    send_bug_report,
    _make_body,
    _make_title,
)


def test_make_title_short() -> None:
    """Заголовок из короткого описания без изменений."""
    assert _make_title("Падает кнопка") == "Падает кнопка"


def test_make_title_empty() -> None:
    """Пустое описание даёт дефолтный заголовок."""
    assert _make_title("") == "Bug report"
    assert _make_title("   ") == "Bug report"


def test_make_title_truncate() -> None:
    """Длинное описание обрезается до 120 символов."""
    long_ = "a" * 150
    assert len(_make_title(long_)) == 120
    assert _make_title(long_).endswith("...")


def test_make_title_one_line() -> None:
    """Переносы строк заменяются на пробел."""
    assert _make_title("строка\nвторая") == "строка вторая"


def test_make_body() -> None:
    """Тело содержит описание и метаданные."""
    payload = BugReportPayload(
        description="Не работает пуш",
        telegram_user_id=123,
        username="alice",
        user_id=1,
    )
    body = _make_body(payload)
    assert "Не работает пуш" in body
    assert "123" in body
    assert "alice" in body
    assert "1" in body


def test_send_bug_report_no_token() -> None:
    """Без токена отправка не выполняется, возвращается success=False."""
    payload = BugReportPayload(
        description="Баг",
        telegram_user_id=1,
        username=None,
        user_id=1,
    )
    result = send_bug_report(payload, token="", repo="owner/repo")
    assert result.success is False
    assert result.github_issue_url is None
    assert result.error_message is not None


def test_send_bug_report_no_repo() -> None:
    """Без repo отправка не выполняется."""
    payload = BugReportPayload(
        description="Баг",
        telegram_user_id=1,
        username=None,
        user_id=1,
    )
    result = send_bug_report(payload, token="secret", repo="")
    assert result.success is False


def test_create_github_issue_no_token_returns_none() -> None:
    """Без токена create_github_issue возвращает None."""
    assert create_github_issue("t", "b", token="", repo="x/y") is None


def test_create_github_issue_success() -> None:
    """При HTTP 201 возвращается html_url из ответа."""
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "html_url": "https://github.com/po4apo/control-habits/issues/1",
    }

    with patch("control_habits.bug_report.service.httpx") as m_httpx:
        m_client = MagicMock()
        m_client.post.return_value = mock_response
        m_client.__enter__ = MagicMock(return_value=m_client)
        m_client.__exit__ = MagicMock(return_value=None)
        m_httpx.Client.return_value = m_client

        out = create_github_issue(
            "Title",
            "Body",
            token="token",
            repo="po4apo/control-habits",
        )

    assert out == "https://github.com/po4apo/control-habits/issues/1"


def test_send_bug_report_success() -> None:
    """При успешном create_github_issue возвращается BugSendResult с url."""
    payload = BugReportPayload(
        description="Не работает кнопка",
        telegram_user_id=456,
        username="bob",
        user_id=2,
    )
    with patch(
        "control_habits.bug_report.service.create_github_issue",
        return_value="https://github.com/po4apo/control-habits/issues/2",
    ):
        result = send_bug_report(
            payload,
            token="token",
            repo="po4apo/control-habits",
        )
    assert result.success is True
    assert result.github_issue_url == "https://github.com/po4apo/control-habits/issues/2"
    assert result.error_message is None
