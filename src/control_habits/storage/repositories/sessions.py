"""Репозиторий активных сессий (интервалы по hotkey)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_habits.storage.models import ActiveSession


class SessionsRepo:
    """Доступ к сессиям. Все времена в UTC."""

    def __init__(self, session: Session) -> None:
        """
        :param session: Сессия SQLAlchemy.
        """
        self._session = session

    def create(
        self,
        user_id: int,
        activity_id: int,
        started_at: datetime,
    ) -> ActiveSession:
        """
        Создать активную сессию.

        :param user_id: Идентификатор пользователя.
        :param activity_id: Идентификатор активности.
        :param started_at: Время старта (UTC).
        :returns: Созданная модель ActiveSession.
        """
        session = ActiveSession(
            user_id=user_id,
            activity_id=activity_id,
            started_at=started_at,
        )
        self._session.add(session)
        self._session.flush()
        return session

    def get_by_id(self, session_id: int) -> ActiveSession | None:
        """
        Найти сессию по идентификатору (активную или закрытую).

        :param session_id: Идентификатор сессии.
        :returns: ActiveSession или None.
        """
        return self._session.get(ActiveSession, session_id)

    def get_active(
        self,
        user_id: int,
        activity_id: int,
    ) -> ActiveSession | None:
        """
        Найти активную сессию (ended_at IS NULL) по пользователю и активности.

        :param user_id: Идентификатор пользователя.
        :param activity_id: Идентификатор активности.
        :returns: ActiveSession или None.
        """
        stmt = (
            select(ActiveSession)
            .where(ActiveSession.user_id == user_id)
            .where(ActiveSession.activity_id == activity_id)
            .where(ActiveSession.ended_at.is_(None))
            .limit(1)
        )
        return self._session.scalar(stmt)

    def list_active(self, user_id: int) -> list[ActiveSession]:
        """
        Список всех активных сессий пользователя (ended_at IS NULL).

        :param user_id: Идентификатор пользователя.
        :returns: Список ActiveSession.
        """
        stmt = (
            select(ActiveSession)
            .where(ActiveSession.user_id == user_id)
            .where(ActiveSession.ended_at.is_(None))
            .order_by(ActiveSession.started_at)
        )
        return list(self._session.scalars(stmt).all())

    def close(self, session_id: int, ended_at: datetime) -> None:
        """
        Закрыть сессию: установить ended_at.

        :param session_id: Идентификатор записи ActiveSession.
        :param ended_at: Время окончания (UTC).
        """
        session = self._session.get(ActiveSession, session_id)
        if session is not None:
            session.ended_at = ended_at
            self._session.flush()

    def list_closed_in_range(
        self,
        user_id: int,
        utc_from: datetime,
        utc_to: datetime,
    ) -> list[ActiveSession]:
        """
        Закрытые сессии пользователя, пересекающиеся с UTC-интервалом [utc_from, utc_to].

        Учитываются сессии, у которых (started_at, ended_at) пересекается с интервалом:
        started_at < utc_to и ended_at >= utc_from.

        :param user_id: Идентификатор пользователя.
        :param utc_from: Начало интервала (UTC).
        :param utc_to: Конец интервала (UTC).
        :returns: Список ActiveSession с заполненным ended_at, по started_at.
        """
        stmt = (
            select(ActiveSession)
            .where(ActiveSession.user_id == user_id)
            .where(ActiveSession.ended_at.is_not(None))
            .where(ActiveSession.started_at < utc_to)
            .where(ActiveSession.ended_at >= utc_from)
            .order_by(ActiveSession.started_at)
        )
        return list(self._session.scalars(stmt).all())
