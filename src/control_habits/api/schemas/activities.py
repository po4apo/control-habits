"""Pydantic-схемы для API активностей и hotkey-кнопок."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ActivityKind = Literal["hotkey", "regular"]


class ActivityCreate(BaseModel):
    """Тело запроса создания активности."""

    name: str = Field(..., min_length=1, max_length=256, description="Название активности")
    kind: ActivityKind = Field(..., description="hotkey — кнопка в боте, regular — без кнопки")


class ActivityUpdate(BaseModel):
    """Тело запроса обновления активности (опциональные поля)."""

    name: str | None = Field(None, min_length=1, max_length=256)
    kind: ActivityKind | None = Field(None)


class ActivityResponse(BaseModel):
    """Ответ: активность."""

    id: int
    name: str
    kind: str

    model_config = {"from_attributes": True}


class HotkeyCreate(BaseModel):
    """Тело запроса добавления hotkey-кнопки: выбор существующей активности или создание новой."""

    activity_id: int | None = Field(
        None,
        description="ID существующей активности (если не задано — создать по name)",
    )
    name: str | None = Field(
        None,
        min_length=1,
        max_length=128,
        description="Название для новой активности (если activity_id не задан)",
    )

    @model_validator(mode="after")
    def require_activity_or_name(self) -> "HotkeyCreate":
        if self.activity_id is not None and self.name is not None:
            raise ValueError("Укажите либо activity_id, либо name")
        if self.activity_id is None and (not self.name or not self.name.strip()):
            raise ValueError("Укажите activity_id или name")
        return self


class HotkeyResponse(BaseModel):
    """Ответ: hotkey-кнопка."""

    id: int
    activity_id: int
    label: str
    order: int
    name: str = ""

    model_config = {"from_attributes": True}


class HotkeyReorderBody(BaseModel):
    """Тело запроса изменения порядка hotkey-кнопок."""

    hotkey_ids: list[int] = Field(
        ...,
        description="Список id hotkey в нужном порядке (индекс = новый order)",
    )
