"""Сервис отправки баг-репортов в GitHub Issues."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_LABELS = ["bug", "from-bot"]


@dataclass
class BugReportPayload:
    """Данные баг-репорта для отправки."""

    description: str
    telegram_user_id: int
    username: str | None
    user_id: int


@dataclass
class BugSendResult:
    """Результат отправки бага."""

    success: bool
    github_issue_url: str | None
    error_message: str | None


def create_github_issue(
    title: str,
    body: str,
    *,
    token: str,
    repo: str,
    labels: list[str] | None = None,
) -> str | None:
    """
    Создать Issue в GitHub через REST API.

    Переменные окружения: GITHUB_TOKEN (Personal Access Token с правами public_repo/repo),
    GITHUB_REPO (owner/repo). Опционально: GITHUB_LABELS (через запятую).

    :param title: Заголовок Issue.
    :param body: Тело Issue (Markdown).
    :param token: GitHub Personal Access Token.
    :param repo: Репозиторий в формате owner/repo.
    :param labels: Метки для Issue; по умолчанию ["bug", "from-bot"].
    :returns: URL созданного Issue (html_url) или None при ошибке.
    """
    if not token or not repo:
        logger.warning("create_github_issue: GITHUB_TOKEN или GITHUB_REPO не заданы")
        return None
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    label_list = labels if labels is not None else DEFAULT_LABELS
    payload = {"title": title, "body": body, "labels": label_list}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload, headers=headers)
        if resp.status_code == 201:
            data = resp.json()
            return data.get("html_url") or data.get("url")
        logger.warning(
            "create_github_issue: HTTP %s, %s",
            resp.status_code,
            resp.text[:200],
        )
        return None
    except Exception as e:
        logger.exception("create_github_issue: %s", e)
        return None


def _make_title(description: str, max_len: int = 120) -> str:
    """Короткий заголовок из описания (одна строка, без переносов)."""
    one_line = description.strip().replace("\n", " ").replace("\r", " ")
    if len(one_line) <= max_len:
        return one_line or "Bug report"
    return one_line[: max_len - 3].rstrip() + "..."


def _make_body(payload: BugReportPayload) -> str:
    """Тело Issue: описание + метаданные."""
    parts = [payload.description, "", "---", ""]
    parts.append(f"- **telegram_user_id**: {payload.telegram_user_id}")
    parts.append(f"- **username**: {payload.username or '—'}")
    parts.append(f"- **user_id** (internal): {payload.user_id}")
    parts.append(f"- **Время**: {datetime.now(timezone.utc).isoformat()}")
    return "\n".join(parts)


def send_bug_report(
    payload: BugReportPayload,
    *,
    token: str,
    repo: str,
    labels: list[str] | None = None,
) -> BugSendResult:
    """
    Сформировать title/body и создать GitHub Issue.

    :param payload: Данные баг-репорта.
    :param token: GitHub PAT.
    :param repo: owner/repo.
    :param labels: Опциональные метки.
    :returns: Результат отправки (URL при успехе).
    """
    title = _make_title(payload.description)
    body = _make_body(payload)
    url = create_github_issue(
        title=title,
        body=body,
        token=token,
        repo=repo,
        labels=labels,
    )
    if url:
        return BugSendResult(success=True, github_issue_url=url, error_message=None)
    return BugSendResult(
        success=False,
        github_issue_url=None,
        error_message="Не удалось создать Issue в GitHub",
    )
