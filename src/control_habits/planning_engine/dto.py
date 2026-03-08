"""DTO и типы для модуля planning_engine."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from control_habits.schedule_model.dto import PlannedItem

NotificationJobType = Literal["task_prompt", "event_start", "event_end"]


@dataclass(frozen=True)
class NotificationJob:
    """
    Задача на отправку пуша: когда отправить и какие данные для сообщения.

    :param planned_at: Момент отправки в UTC.
    :param type: Тип уведомления (task_prompt | event_start | event_end).
    :param plan_item_id: Идентификатор элемента плана.
    :param idempotency_key: Уникальный ключ (plan_item_id + date + type) для идемпотентности.
    :param planned_item: Развёрнутый элемент плана — данные для сборки сообщения.
    """

    planned_at: datetime  # UTC
    type: NotificationJobType
    plan_item_id: int
    idempotency_key: str
    planned_item: PlannedItem
