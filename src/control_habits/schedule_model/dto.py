"""DTO и типы для модуля schedule_model."""

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import IntEnum
from typing import Literal

PlannedItemType = Literal["task", "event_start", "event_end"]


class DayOfWeek(IntEnum):
    """
    День недели (ISO 8601: 1 = понедельник, 7 = воскресенье).

    Используется для проверки days_of_week в элементах плана.
    """

    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7


@dataclass(frozen=True)
class TaskItem:
    """
    Дело: одна точка времени в день, дни недели, название.

    :param kind: Всегда "task".
    :param title: Название дела.
    :param start_time: Время в рамках дня (локальное время пользователя).
    :param end_time: Для задачи не используется или равно start_time.
    :param days_of_week: Список дней недели 1–7 (ISO).
    :param activity_id: Идентификатор активности или None.
    """

    kind: str  # "task"
    title: str
    start_time: time
    end_time: time
    days_of_week: list[int]  # 1–7 (ISO)
    activity_id: int | None

    def __post_init__(self) -> None:
        if self.kind != "task":
            raise ValueError("TaskItem.kind должен быть 'task'")


@dataclass(frozen=True)
class EventItem:
    """
    Событие: блок времени в день, дни недели, название.

    :param kind: Всегда "event".
    :param title: Название события.
    :param start_time: Начало в рамках дня (локальное время).
    :param end_time: Конец в рамках дня (локальное время).
    :param days_of_week: Список дней недели 1–7 (ISO).
    :param activity_id: Идентификатор активности или None.
    """

    kind: str  # "event"
    title: str
    start_time: time
    end_time: time
    days_of_week: list[int]  # 1–7 (ISO)
    activity_id: int | None

    def __post_init__(self) -> None:
        if self.kind != "event":
            raise ValueError("EventItem.kind должен быть 'event'")


@dataclass(frozen=True)
class ScheduleTemplate:
    """
    Шаблон расписания (DTO).

    :param id: Идентификатор шаблона.
    :param name: Название шаблона.
    """

    id: int
    name: str


@dataclass(frozen=True)
class PlannedItem:
    """
    Элемент плана, развёрнутый на конкретную дату (время в UTC).

    :param plan_item_id: Идентификатор элемента плана (plan_items.id).
    :param date: Дата плана.
    :param planned_at: Момент времени в UTC (старт для task/event_start, конец для event_end).
    :param type: "task" | "event_start" | "event_end".
    """

    plan_item_id: int
    date: date
    planned_at: datetime  # UTC
    type: PlannedItemType
