"""Репозиторий расписаний и шаблонов."""

from datetime import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_habits.storage.models import PlanItem, ScheduleTemplate

_UNSET: Any = object()


class ScheduleRepo:
    """Доступ к шаблонам расписания и элементам плана. Все времена в UTC."""

    def __init__(self, session: Session) -> None:
        """
        :param session: Сессия SQLAlchemy.
        """
        self._session = session

    def get_template(self, user_id: int) -> ScheduleTemplate | None:
        """
        Получить (первый) шаблон расписания пользователя.

        В MVP у пользователя один активный шаблон — возвращается первый по id.

        :param user_id: Идентификатор пользователя.
        :returns: Шаблон или None.
        """
        stmt = (
            select(ScheduleTemplate)
            .where(ScheduleTemplate.user_id == user_id)
            .order_by(ScheduleTemplate.id)
            .limit(1)
        )
        return self._session.scalar(stmt)

    def get_template_by_id(self, template_id: int) -> ScheduleTemplate | None:
        """
        Получить шаблон по id.

        :param template_id: Идентификатор шаблона.
        :returns: Шаблон или None.
        """
        return self._session.get(ScheduleTemplate, template_id)

    def create_template(self, user_id: int, name: str) -> ScheduleTemplate:
        """
        Создать шаблон расписания.

        :param user_id: Идентификатор пользователя.
        :param name: Название шаблона.
        :returns: Созданная модель ScheduleTemplate.
        """
        template = ScheduleTemplate(user_id=user_id, name=name)
        self._session.add(template)
        self._session.flush()
        return template

    def update_template(self, template_id: int, name: str) -> None:
        """
        Обновить название шаблона.

        :param template_id: Идентификатор шаблона.
        :param name: Новое название.
        """
        template = self._session.get(ScheduleTemplate, template_id)
        if template is not None:
            template.name = name

    def delete_template(self, template_id: int) -> None:
        """
        Удалить шаблон и все его элементы плана (каскад).

        :param template_id: Идентификатор шаблона.
        """
        template = self._session.get(ScheduleTemplate, template_id)
        if template is not None:
            self._session.delete(template)

    def get_plan_items(self, template_id: int) -> list[PlanItem]:
        """
        Получить все элементы плана шаблона.

        :param template_id: Идентификатор шаблона.
        :returns: Список PlanItem (порядок по id).
        """
        stmt = (
            select(PlanItem)
            .where(PlanItem.template_id == template_id)
            .order_by(PlanItem.id)
        )
        return list(self._session.scalars(stmt).all())

    def get_plan_item(self, plan_item_id: int) -> PlanItem | None:
        """
        Получить элемент плана по id.

        :param plan_item_id: Идентификатор элемента плана.
        :returns: PlanItem или None.
        """
        return self._session.get(PlanItem, plan_item_id)

    def create_plan_item(
        self,
        template_id: int,
        kind: str,
        title: str,
        start_time: time,
        end_time: time,
        days_of_week: list[int],
        activity_id: int | None = None,
    ) -> PlanItem:
        """
        Создать элемент плана (task или event).

        :param template_id: Идентификатор шаблона.
        :param kind: Тип: task или event.
        :param title: Название.
        :param start_time: Время начала в рамках дня (локальное время пользователя).
        :param end_time: Время конца (для task можно передать то же, что start_time).
        :param days_of_week: Дни недели 1–7 (ISO).
        :param activity_id: Идентификатор активности или None.
        :returns: Созданная модель PlanItem.
        """
        item = PlanItem(
            template_id=template_id,
            kind=kind,
            title=title,
            start_time=start_time,
            end_time=end_time,
            days_of_week=days_of_week,
            activity_id=activity_id,
        )
        self._session.add(item)
        self._session.flush()
        return item

    def update_plan_item(
        self,
        plan_item_id: int,
        *,
        title: str | None = None,
        start_time: time | None = None,
        end_time: time | None = None,
        days_of_week: list[int] | None = None,
        activity_id: int | None | Any = _UNSET,
    ) -> None:
        """
        Обновить элемент плана (переданные поля).

        :param plan_item_id: Идентификатор элемента плана.
        :param title: Новое название (опционально).
        :param start_time: Новое время начала (опционально).
        :param end_time: Новое время конца (опционально).
        :param days_of_week: Новые дни недели (опционально).
        :param activity_id: Идентификатор активности; если не передано — не менять; явно None — сбросить.
        """
        item = self._session.get(PlanItem, plan_item_id)
        if item is None:
            return
        if title is not None:
            item.title = title
        if start_time is not None:
            item.start_time = start_time
        if end_time is not None:
            item.end_time = end_time
        if days_of_week is not None:
            item.days_of_week = days_of_week
        if activity_id is not _UNSET:
            item.activity_id = activity_id

    def delete_plan_item(self, plan_item_id: int) -> None:
        """
        Удалить элемент плана по id.

        :param plan_item_id: Идентификатор элемента плана.
        """
        item = self._session.get(PlanItem, plan_item_id)
        if item is not None:
            self._session.delete(item)

    def list_by_user(self, user_id: int) -> list[ScheduleTemplate]:
        """
        Список всех шаблонов пользователя.

        :param user_id: Идентификатор пользователя.
        :returns: Список шаблонов (по id).
        """
        stmt = (
            select(ScheduleTemplate)
            .where(ScheduleTemplate.user_id == user_id)
            .order_by(ScheduleTemplate.id)
        )
        return list(self._session.scalars(stmt).all())

    def list_user_ids_with_templates(self) -> list[int]:
        """
        Список user_id, у которых есть хотя бы один шаблон расписания.

        Нужно для планировщика пушей: заполнять очередь уведомлений по всем пользователям с расписанием.

        :returns: Список уникальных user_id.
        """
        stmt = select(ScheduleTemplate.user_id).distinct()
        return list(self._session.scalars(stmt).all())
