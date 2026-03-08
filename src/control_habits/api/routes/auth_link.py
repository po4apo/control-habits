"""Эндпоинты привязки аккаунта: создание кода и проверка статуса."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from control_habits.api.deps import get_auth_linking_service, get_settings
from control_habits.auth_linking import AuthLinkingService
from control_habits.config import Settings

router = APIRouter(prefix="/auth", tags=["auth"])


class CreateLinkCodeBody(BaseModel):
    """Тело запроса создания кода привязки."""

    web_session_id: str | None = Field(
        default=None,
        description="Идентификатор веб-сессии; если не передан — генерируется.",
    )


class CreateLinkCodeResponse(BaseModel):
    """Ответ: код и ссылка на бота."""

    code: str = Field(..., description="Одноразовый код привязки.")
    link: str = Field(
        ...,
        description="Ссылка вида t.me/<bot>?start=<code> для перехода в бота.",
    )
    web_session_id: str = Field(
        ...,
        description="Идентификатор сессии (переданный или сгенерированный) для последующего polling.",
    )


class LinkStatusResponse(BaseModel):
    """Ответ проверки статуса привязки."""

    status: str = Field(
        ...,
        description="pending | consumed | expired | not_found.",
    )


@router.post(
    "/link-code",
    response_model=CreateLinkCodeResponse,
    summary="Создать код привязки",
    description="Создаёт одноразовый код и возвращает его и ссылку на бота для подтверждения в Telegram.",
)
def create_link_code(
    body: CreateLinkCodeBody | None = None,
    service: AuthLinkingService = Depends(get_auth_linking_service),
    settings: Settings = Depends(get_settings),
) -> CreateLinkCodeResponse:
    """
    Создать код привязки.

    :param body: Опционально web_session_id (иначе генерируется).
    :param service: Сервис привязки.
    :param settings: Настройки (bot_username для ссылки).
    :returns: Код, ссылка t.me/<bot>?start=<code> и web_session_id.
    """
    web_session_id = (
        (body or CreateLinkCodeBody()).web_session_id
        or str(uuid.uuid4())
    )
    code = service.create_link_code(web_session_id=web_session_id)
    bot = (settings.bot_username or "bot").strip().lstrip("@")
    link = f"https://t.me/{bot}?start={code}" if bot else f"https://t.me/?start={code}"
    return CreateLinkCodeResponse(
        code=code,
        link=link,
        web_session_id=web_session_id,
    )


@router.get(
    "/link-status",
    response_model=LinkStatusResponse,
    summary="Проверить статус привязки",
    description="Для polling фронтом: по коду или по web_session_id.",
)
def get_link_status(
    code: str | None = Query(None, description="Код привязки."),
    web_session_id: str | None = Query(
        None,
        alias="web_session_id",
        description="Идентификатор веб-сессии (последний созданный код для этой сессии).",
    ),
    service: AuthLinkingService = Depends(get_auth_linking_service),
) -> LinkStatusResponse:
    """
    Проверить статус привязки по коду или по web_session_id.

    Должен быть передан ровно один из параметров: code или web_session_id.

    :param code: Код привязки.
    :param web_session_id: Идентификатор веб-сессии.
    :param service: Сервис привязки.
    :returns: Статус: pending | consumed | expired | not_found.
    """
    if code and web_session_id:
        raise HTTPException(
            status_code=400,
            detail="Передайте только code или только web_session_id",
        )
    if not code and not web_session_id:
        raise HTTPException(
            status_code=400,
            detail="Передайте code или web_session_id",
        )

    if code:
        status = service.get_link_status(code)
    else:
        status, _ = service.get_link_status_by_session(web_session_id or "")

    return LinkStatusResponse(status=status)