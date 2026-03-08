"""Pydantic-схемы для API расписания и элементов плана."""

from datetime import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _parse_time(v: str) -> time:
    """Парсинг времени из строки HH:MM или HH:MM:SS (локальное время пользователя)."""
    parts = v.strip().split(":")
    if len(parts) == 2:
        h, m = int(parts[0]), int(parts[1])
        return time(h, m)
    if len(parts) == 3:
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        return time(h, m, s)
    raise ValueError("Время в формате HH:MM или HH:MM:SS")


def _time_serialize(t: time) -> str:
    """Сериализация time в строку HH:MM."""
    return t.strftime("%H:%M")


# --- Шаблон ---


class ScheduleTemplateCreate(BaseModel):
    """Тело запроса создания шаблона расписания."""

    name: str = Field(..., min_length=1, max_length=256, description="Название шаблона")


class ScheduleTemplateUpdate(BaseModel):
    """Тело запроса обновления шаблона (только название)."""

    name: str = Field(..., min_length=1, max_length=256, description="Название шаблона")


class ScheduleTemplateResponse(BaseModel):
    """Ответ: шаблон расписания."""

    id: int
    name: str

    model_config = {"from_attributes": True}


# --- Элемент плана (TaskItem / EventItem) ---

PlanItemKind = Literal["task", "event"]


class PlanItemCreate(BaseModel):
    """
    Тело запроса создания элемента плана (дело или событие).

    Время — в локальном времени пользователя (в рамках дня). В БД хранится как время дня;
    при планировании пушей используется timezone пользователя для перевода в UTC.
    """

    kind: PlanItemKind = Field(..., description="task — дело, event — событие")
    title: str = Field(..., min_length=1, max_length=512)
    start_time: str = Field(..., description="Время начала в формате HH:MM или HH:MM:SS (локальное)")
    end_time: str = Field(..., description="Время конца (для task можно совпадать с start_time)")
    days_of_week: list[int] = Field(
        ...,
        min_length=1,
        description="Дни недели 1–7 (ISO: 1=пн, 7=вс)",
    )
    activity_id: int | None = Field(None, description="Идентификатор активности или null")

    @field_validator("start_time", "end_time")
    @classmethod
    def parse_time_str(cls, v: str) -> str:
        """Валидация формата времени (проверка при создании)."""
        _parse_time(v)
        return v

    @field_validator("days_of_week")
    @classmethod
    def days_in_range(cls, v: list[int]) -> list[int]:
        """Дни недели от 1 до 7."""
        if not all(1 <= d <= 7 for d in v):
            raise ValueError("Дни недели должны быть от 1 до 7")
        return v


class PlanItemUpdate(BaseModel):
    """Тело запроса обновления элемента плана (все поля опциональны)."""

    title: str | None = Field(None, min_length=1, max_length=512)
    start_time: str | None = Field(None, description="HH:MM или HH:MM:SS")
    end_time: str | None = Field(None, description="HH:MM или HH:MM:SS")
    days_of_week: list[int] | None = Field(None, min_length=1)
    activity_id: int | None = Field(None)  # явно null — сбросить связь

    @field_validator("start_time", "end_time")
    @classmethod
    def parse_time_str(cls, v: str | None) -> str | None:
        if v is None:
            return None
        _parse_time(v)
        return v

    @field_validator("days_of_week")
    @classmethod
    def days_in_range(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        if not all(1 <= d <= 7 for d in v):
            raise ValueError("Дни недели должны быть от 1 до 7")
        return v


class PlanItemResponse(BaseModel):
    """Ответ: элемент плана (TaskItem или EventItem)."""

    id: int
    template_id: int
    kind: str
    title: str
    start_time: str  # локальное время дня, HH:MM
    end_time: str
    days_of_week: list[int]
    activity_id: int | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_item(cls, item: object) -> "PlanItemResponse":
        """Собрать ответ из ORM PlanItem (start_time/end_time — time, сериализуем в строку)."""
        from control_habits.storage.models import PlanItem

        o = item
        if not isinstance(o, PlanItem):
            raise TypeError("Ожидается PlanItem")
        return cls(
            id=o.id,
            template_id=o.template_id,
            kind=o.kind,
            title=o.title,
            start_time=_time_serialize(o.start_time),
            end_time=_time_serialize(o.end_time),
            days_of_week=list(o.days_of_week),
            activity_id=o.activity_id,
        )
