"""Pydantic-схемы для API отчёта за день."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class PlannedItemResponse(BaseModel):
    """Элемент плана на дату (для отчёта)."""

    plan_item_id: int
    date: date
    planned_at: datetime = Field(..., description="Момент в UTC (старт или конец)")
    type: str = Field(..., description="task | event_start | event_end")
    title: str = Field("", description="Название элемента плана")
    start_time: str = Field("", description="Время начала (HH:MM) в локальном дне")
    end_time: str = Field("", description="Время конца (HH:MM) в локальном дне")


class AnswerFactResponse(BaseModel):
    """Факт ответа/действия пользователя для отчёта."""

    responded_at: datetime = Field(..., description="Время ответа (UTC)")
    action: str
    plan_item_id: int | None = None
    activity_id: int | None = None
    payload: dict[str, Any] | None = None


class SessionIntervalResponse(BaseModel):
    """Интервал закрытой сессии для отчёта."""

    started_at: datetime = Field(..., description="Начало сессии (UTC)")
    ended_at: datetime = Field(..., description="Конец сессии (UTC)")
    duration_seconds: float = Field(..., description="Длительность в секундах")
    activity_id: int
    activity_name: str = Field("", description="Название активности")


class DailyReportResponse(BaseModel):
    """
    Отчёт за один календарный день (в локальном времени пользователя).

    :param planned: Запланированные элементы на дату.
    :param answers: Факты ответов (время и action).
    :param intervals: Закрытые сессии за дату с длительностями.
    """

    planned: list[PlannedItemResponse] = Field(default_factory=list)
    answers: list[AnswerFactResponse] = Field(default_factory=list)
    intervals: list[SessionIntervalResponse] = Field(default_factory=list)
