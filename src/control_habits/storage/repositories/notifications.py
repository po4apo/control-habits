"""Репозиторий уведомлений (запланированные пуши)."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from control_habits.storage.models import Notification


class NotificationsRepo:
    """Доступ к уведомлениям. Все времена в UTC."""

    def __init__(self, session: Session) -> None:
        """
        :param session: Сессия SQLAlchemy.
        """
        self._session = session

    def create_many(
        self,
        records: list[dict[str, Any]],
    ) -> None:
        """
        Создать несколько записей уведомлений.

        Каждый элемент records — словарь с ключами: user_id, plan_item_id,
        planned_at (datetime UTC), type, idempotency_key.

        :param records: Список словарей с полями уведомления.
        """
        for r in records:
            n = Notification(
                user_id=r["user_id"],
                plan_item_id=r["plan_item_id"],
                planned_at=r["planned_at"],
                type=r["type"],
                idempotency_key=r["idempotency_key"],
            )
            self._session.add(n)
        self._session.flush()

    def create_many_ignore_duplicates(
        self,
        records: list[dict[str, Any]],
    ) -> None:
        """
        Вставить уведомления; при конфликте по idempotency_key строку не вставлять.

        Используется планировщиком при заполнении очереди на день: повторный вызов
        для тех же (user_id, date) не создаёт дубликаты.

        :param records: Список словарей с полями user_id, plan_item_id, planned_at, type, idempotency_key.
        """
        if not records:
            return
        stmt = pg_insert(Notification).values(records).on_conflict_do_nothing(
            index_elements=["idempotency_key"],
        )
        self._session.execute(stmt)
        self._session.flush()

    def get_pending(self, until: datetime) -> list[Notification]:
        """
        Выбрать уведомления к отправке: planned_at <= until, sent_at IS NULL.

        :param until: Верхняя граница времени (UTC) для planned_at.
        :returns: Список Notification (порядок по planned_at).
        """
        stmt = (
            select(Notification)
            .where(Notification.planned_at <= until)
            .where(Notification.sent_at.is_(None))
            .order_by(Notification.planned_at, Notification.id)
        )
        return list(self._session.scalars(stmt).all())

    def get_pending_locked(self, until: datetime) -> list[Notification]:
        """
        Выбрать уведомления к отправке с блокировкой строк (FOR UPDATE SKIP LOCKED).

        Для работы при нескольких инстансах: только один воркер получит строку.
        Вызывать в рамках активной транзакции; блокировка держится до commit/rollback.

        :param until: Верхняя граница времени (UTC) для planned_at.
        :returns: Список Notification (порядок по planned_at).
        """
        stmt = (
            select(Notification)
            .where(Notification.planned_at <= until)
            .where(Notification.sent_at.is_(None))
            .order_by(Notification.planned_at, Notification.id)
            .with_for_update(skip_locked=True)
        )
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, notification_id: int) -> Notification | None:
        """
        Получить уведомление по идентификатору.

        :param notification_id: Идентификатор уведомления.
        :returns: Модель Notification или None.
        """
        return self._session.get(Notification, notification_id)

    def mark_sent(self, notification_id: int, sent_at: datetime) -> None:
        """
        Пометить уведомление отправленным.

        :param notification_id: Идентификатор уведомления.
        :param sent_at: Время отправки (UTC).
        """
        notification = self._session.get(Notification, notification_id)
        if notification is not None:
            notification.sent_at = sent_at
