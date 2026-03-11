"""Репозиторий черновиков баг-репортов."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_habits.storage.models import BugReportDraft

STATE_WAITING_DESCRIPTION = "waiting_description"
STATE_WAITING_CONFIRM = "waiting_confirm"
STATE_SENT = "sent"
STATE_CANCELLED = "cancelled"


class BugReportDraftRepo:
    """Доступ к черновикам баг-репортов. Один активный черновик на пользователя."""

    def __init__(self, session: Session) -> None:
        """
        :param session: Сессия SQLAlchemy.
        """
        self._session = session

    def get_active_by_telegram_id(self, telegram_user_id: int) -> BugReportDraft | None:
        """
        Найти активный черновик (ожидание описания или подтверждения).

        :param telegram_user_id: Идентификатор пользователя в Telegram.
        :returns: Черновик или None.
        """
        stmt = (
            select(BugReportDraft)
            .where(BugReportDraft.telegram_user_id == telegram_user_id)
            .where(
                BugReportDraft.state.in_(
                    [STATE_WAITING_DESCRIPTION, STATE_WAITING_CONFIRM]
                )
            )
            .order_by(BugReportDraft.updated_at.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def create(self, user_id: int, telegram_user_id: int) -> BugReportDraft:
        """
        Создать черновик в состоянии ожидания описания.

        :param user_id: Внутренний id пользователя.
        :param telegram_user_id: Telegram user id.
        :returns: Созданный черновик.
        """
        now = datetime.now(timezone.utc)
        draft = BugReportDraft(
            user_id=user_id,
            telegram_user_id=telegram_user_id,
            description="",
            state=STATE_WAITING_DESCRIPTION,
            created_at=now,
            updated_at=now,
            github_issue_url=None,
        )
        self._session.add(draft)
        self._session.flush()
        return draft

    def update_description(self, draft_id: int, description: str) -> BugReportDraft | None:
        """
        Сохранить описание и перевести в состояние ожидания подтверждения.

        :param draft_id: Id черновика.
        :param description: Текст описания бага.
        :returns: Обновлённый черновик или None.
        """
        draft = self._session.get(BugReportDraft, draft_id)
        if draft is None:
            return None
        draft.description = description[:4096]
        draft.state = STATE_WAITING_CONFIRM
        draft.updated_at = datetime.now(timezone.utc)
        self._session.flush()
        return draft

    def get_by_id(self, draft_id: int) -> BugReportDraft | None:
        """
        Получить черновик по id.

        :param draft_id: Id черновика.
        :returns: Черновик или None.
        """
        return self._session.get(BugReportDraft, draft_id)

    def mark_sent(self, draft_id: int, github_issue_url: str) -> None:
        """
        Отметить черновик как отправленный, сохранить URL Issue.

        :param draft_id: Id черновика.
        :param github_issue_url: Ссылка на созданный GitHub Issue.
        """
        draft = self._session.get(BugReportDraft, draft_id)
        if draft is not None:
            draft.state = STATE_SENT
            draft.github_issue_url = github_issue_url[:512]
            draft.updated_at = datetime.now(timezone.utc)

    def mark_cancelled(self, draft_id: int) -> None:
        """
        Отменить черновик.

        :param draft_id: Id черновика.
        """
        draft = self._session.get(BugReportDraft, draft_id)
        if draft is not None:
            draft.state = STATE_CANCELLED
            draft.updated_at = datetime.now(timezone.utc)
