"""Репозиторий логов (факты ответов и действий)."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from control_habits.storage.models import LogEntry


class LogsRepo:
    """Доступ к лог-записям. Все времена в UTC."""

    def __init__(self, session: Session) -> None:
        """
        :param session: Сессия SQLAlchemy.
        """
        self._session = session

    def add(
        self,
        user_id: int,
        responded_at: Any,
        action: str,
        plan_item_id: int | None = None,
        activity_id: int | None = None,
        planned_at: Any = None,
        payload: dict[str, Any] | None = None,
    ) -> LogEntry:
        """
        Добавить запись в лог.

        :param user_id: Идентификатор пользователя.
        :param responded_at: Время ответа/действия (UTC, datetime).
        :param action: Тип действия (task_done, session_start и т.д.).
        :param plan_item_id: Опционально — элемент плана.
        :param activity_id: Опционально — активность.
        :param planned_at: Опционально — запланированное время.
        :param payload: Опционально — доп. данные (в т.ч. idempotency_key для проверки дублей).
        :returns: Созданная модель LogEntry.
        """
        entry = LogEntry(
            user_id=user_id,
            plan_item_id=plan_item_id,
            activity_id=activity_id,
            planned_at=planned_at,
            responded_at=responded_at,
            action=action,
            payload=payload,
        )
        self._session.add(entry)
        self._session.flush()
        return entry

    def exists_by_idempotency_key(self, idempotency_key: str) -> bool:
        """
        Проверить, есть ли уже запись с данным ключом идемпотентности.

        Ключ ищется в payload['idempotency_key'] (JSONB).

        :param idempotency_key: Ключ идемпотентности (например plan_item_id + date + type).
        :returns: True, если такая запись есть.
        """
        stmt = (
            select(LogEntry.id)
            .where(
                func.jsonb_extract_path_text(LogEntry.payload, "idempotency_key")
                == idempotency_key
            )
            .limit(1)
        )
        return self._session.scalar(stmt) is not None

    def list_by_user_and_date_range(
        self,
        user_id: int,
        utc_from_inclusive: datetime,
        utc_to_exclusive: datetime,
    ) -> list[LogEntry]:
        """
        Список записей лога пользователя за UTC-интервал [utc_from, utc_to).

        :param user_id: Идентификатор пользователя.
        :param utc_from_inclusive: Начало интервала (UTC, включительно).
        :param utc_to_exclusive: Конец интервала (UTC, не включительно).
        :returns: Список LogEntry, отсортированный по responded_at.
        """
        stmt = (
            select(LogEntry)
            .where(LogEntry.user_id == user_id)
            .where(LogEntry.responded_at >= utc_from_inclusive)
            .where(LogEntry.responded_at < utc_to_exclusive)
            .order_by(LogEntry.responded_at)
        )
        return list(self._session.scalars(stmt).all())

    def list_planned_events_in_progress(
        self,
        user_id: int,
        utc_from_inclusive: datetime,
        utc_to_exclusive: datetime,
    ) -> list[tuple[int, datetime]]:
        """
        Запланированные события (из расписания), которые «начаты» и ещё не «закончены» в интервале.

        Ищет event_started с plan_item_id за период; исключает plan_item_id, по которым
        есть event_ended или event_skipped в том же периоде.

        :param user_id: Идентификатор пользователя.
        :param utc_from_inclusive: Начало интервала (UTC, включительно).
        :param utc_to_exclusive: Конец интервала (UTC, не включительно).
        :returns: Список пар (plan_item_id, started_at), где started_at — responded_at записи event_started.
        """
        started = (
            select(LogEntry.plan_item_id, LogEntry.responded_at)
            .where(LogEntry.user_id == user_id)
            .where(LogEntry.responded_at >= utc_from_inclusive)
            .where(LogEntry.responded_at < utc_to_exclusive)
            .where(LogEntry.action == "event_started")
            .where(LogEntry.plan_item_id.isnot(None))
        )
        started_rows = list(self._session.execute(started).all())

        ended_plan_ids = set(
            self._session.scalars(
                select(LogEntry.plan_item_id)
                .where(LogEntry.user_id == user_id)
                .where(LogEntry.responded_at >= utc_from_inclusive)
                .where(LogEntry.responded_at < utc_to_exclusive)
                .where(LogEntry.action.in_(["event_ended", "event_skipped"]))
                .where(LogEntry.plan_item_id.isnot(None))
                .distinct()
            ).all()
        )

        return [
            (int(plan_item_id), responded_at)
            for plan_item_id, responded_at in started_rows
            if plan_item_id is not None and plan_item_id not in ended_plan_ids
        ]
