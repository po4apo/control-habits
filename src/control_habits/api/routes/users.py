"""Эндпоинты текущего пользователя: настройки (часовой пояс)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from control_habits.api.deps import get_current_user_id, get_users_repo
from control_habits.storage.repositories.users import UsersRepo

router = APIRouter(prefix="/users", tags=["users"])


class UserSettingsResponse(BaseModel):
    """Ответ: настройки текущего пользователя."""

    timezone: str = Field(..., description="IANA часовой пояс (например Europe/Moscow)")


class UserSettingsUpdate(BaseModel):
    """Тело запроса обновления настроек (часовой пояс)."""

    timezone: str | None = Field(
        None,
        min_length=1,
        max_length=64,
        description="IANA timezone (например Europe/Moscow)",
    )


@router.get(
    "/me",
    response_model=UserSettingsResponse,
    summary="Настройки текущего пользователя",
)
def get_me(
    user_id: int = Depends(get_current_user_id),
    users_repo: UsersRepo = Depends(get_users_repo),
) -> UserSettingsResponse:
    """
    Получить настройки текущего пользователя (часовой пояс).

    :param user_id: Идентификатор пользователя из сессии.
    :param users_repo: Репозиторий пользователей.
    :returns: Настройки пользователя.
    """
    user = users_repo.get_by_id(user_id)
    if user is None:
        raise RuntimeError("Пользователь не найден после авторизации")
    return UserSettingsResponse(timezone=user.timezone)


@router.patch(
    "/me",
    response_model=UserSettingsResponse,
    summary="Обновить настройки пользователя",
)
def update_me(
    body: UserSettingsUpdate,
    user_id: int = Depends(get_current_user_id),
    users_repo: UsersRepo = Depends(get_users_repo),
) -> UserSettingsResponse:
    """
    Обновить часовой пояс текущего пользователя.

    :param body: Новый timezone (опционально).
    :param user_id: Идентификатор пользователя из сессии.
    :param users_repo: Репозиторий пользователей.
    :returns: Обновлённые настройки.
    """
    user = users_repo.get_by_id(user_id)
    if user is None:
        raise RuntimeError("Пользователь не найден после авторизации")
    if body.timezone is not None:
        users_repo.update_timezone(user_id, body.timezone)
        return UserSettingsResponse(timezone=body.timezone)
    return UserSettingsResponse(timezone=user.timezone)
