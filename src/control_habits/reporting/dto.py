"""DTO для отчёта за день."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from control_habits.schedule_model.dto import PlannedItem


@dataclass(frozen=True)
class AnswerFact:
    """
    Факт ответа/действия пользователя для отчёта.

    :param responded_at: Время ответа (UTC).
    :param action: Тип действия (task_done, session_start и т.д.).
    :param plan_item_id: Идентификатор элемента плана или None.
    :param activity_id: Идентификатор активности или None.
    :param payload: Дополнительные данные (опционально).
    """

    responded_at: datetime
    action: str
    plan_item_id: int | None
    activity_id: int | None
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class SessionInterval:
    """
    Интервал закрытой сессии для отчёта.

    :param started_at: Начало сессии (UTC).
    :param ended_at: Конец сессии (UTC).
    :param duration_seconds: Длительность в секундах.
    :param activity_id: Идентификатор активности.
    """

    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    activity_id: int


@dataclass(frozen=True)
class DailyReport:
    """
    Отчёт за один день (календарный день в локальном времени пользователя).

    :param planned: Список запланированных элементов на дату (с типами task/event_start/event_end).
    :param answers: Список фактов ответов (время и статус/action).
    :param intervals: Список интервалов — закрытые сессии с started_at/ended_at за эту дату и длительностями.
    """

    planned: list[PlannedItem]
    answers: list[AnswerFact]
    intervals: list[SessionInterval]
