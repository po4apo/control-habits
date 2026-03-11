"""Эндпоинты CRUD активностей и hotkey-кнопок (список, добавление, удаление, reorder)."""

from fastapi import APIRouter, Depends, HTTPException

from control_habits.api.deps import (
    get_activity_repo,
    get_current_user_id,
    get_hotkeys_repo,
)
from control_habits.api.schemas.activities import (
    ActivityCreate,
    ActivityResponse,
    HotkeyCreate,
    HotkeyResponse,
    HotkeyReorderBody,
)
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.hotkeys import HotkeysRepo

router = APIRouter(prefix="/activities", tags=["activities"])


# --- Активности ---


@router.get(
    "",
    response_model=list[ActivityResponse],
    summary="Список активностей",
)
def list_activities(
    user_id: int = Depends(get_current_user_id),
    activity_repo: ActivityRepo = Depends(get_activity_repo),
) -> list[ActivityResponse]:
    """
    Получить список активностей текущего пользователя.

    :param user_id: Идентификатор пользователя из сессии.
    :param activity_repo: Репозиторий активностей.
    :returns: Список активностей.
    """
    activities = activity_repo.list_by_user(user_id)
    return [ActivityResponse.model_validate(a) for a in activities]


@router.post(
    "",
    response_model=ActivityResponse,
    status_code=201,
    summary="Добавить активность",
)
def create_activity(
    body: ActivityCreate,
    user_id: int = Depends(get_current_user_id),
    activity_repo: ActivityRepo = Depends(get_activity_repo),
) -> ActivityResponse:
    """
    Создать активность (hotkey или regular).

    :param body: Название и тип активности.
    :param user_id: Идентификатор пользователя из сессии.
    :param activity_repo: Репозиторий активностей.
    :returns: Созданная активность.
    """
    activity = activity_repo.create(
        user_id=user_id,
        name=body.name,
        kind=body.kind,
    )
    return ActivityResponse.model_validate(activity)


@router.delete(
    "/{activity_id}",
    status_code=204,
    summary="Удалить активность",
)
def delete_activity(
    activity_id: int,
    user_id: int = Depends(get_current_user_id),
    activity_repo: ActivityRepo = Depends(get_activity_repo),
) -> None:
    """
    Удалить активность по id.

    :param activity_id: Идентификатор активности.
    :param user_id: Идентификатор пользователя из сессии.
    :param activity_repo: Репозиторий активностей.
    """
    activity = activity_repo.get_by_id(activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Активность не найдена")
    if activity.user_id != user_id:
        raise HTTPException(status_code=403, detail="Нет доступа к активности")
    activity_repo.delete(activity_id)


# --- Hotkey-кнопки ---


def _hotkey_to_response(hotkey: object, activity_repo: ActivityRepo) -> HotkeyResponse:
    """Собрать HotkeyResponse с подгрузкой имени активности."""
    activity = activity_repo.get_by_id(hotkey.activity_id)  # type: ignore[attr-defined]
    name = activity.name if activity else ""
    resp = HotkeyResponse.model_validate(hotkey)
    resp.name = name
    return resp


@router.get(
    "/hotkeys",
    response_model=list[HotkeyResponse],
    summary="Список hotkey-кнопок",
)
def list_hotkeys(
    user_id: int = Depends(get_current_user_id),
    hotkeys_repo: HotkeysRepo = Depends(get_hotkeys_repo),
    activity_repo: ActivityRepo = Depends(get_activity_repo),
) -> list[HotkeyResponse]:
    """
    Получить список hotkey-кнопок текущего пользователя (отсортированы по order).

    :param user_id: Идентификатор пользователя из сессии.
    :param hotkeys_repo: Репозиторий hotkeys.
    :param activity_repo: Репозиторий активностей.
    :returns: Список hotkey-кнопок с названиями активностей.
    """
    hotkeys = hotkeys_repo.list_by_user(user_id)
    return [_hotkey_to_response(h, activity_repo) for h in hotkeys]


@router.post(
    "/hotkeys",
    response_model=HotkeyResponse,
    status_code=201,
    summary="Добавить hotkey-кнопку",
)
def create_hotkey(
    body: HotkeyCreate,
    user_id: int = Depends(get_current_user_id),
    activity_repo: ActivityRepo = Depends(get_activity_repo),
    hotkeys_repo: HotkeysRepo = Depends(get_hotkeys_repo),
) -> HotkeyResponse:
    """
    Создать hotkey-кнопку по названию: автоматически создаёт Activity (kind=hotkey) и Hotkey.

    :param body: Название кнопки.
    :param user_id: Идентификатор пользователя из сессии.
    :param activity_repo: Репозиторий активностей.
    :param hotkeys_repo: Репозиторий hotkeys.
    :returns: Созданная hotkey-кнопка.
    """
    activity = activity_repo.create(user_id=user_id, name=body.name, kind="hotkey")
    existing = hotkeys_repo.list_by_user(user_id)
    next_order = max((h.order for h in existing), default=-1) + 1
    hotkey = hotkeys_repo.add(
        user_id=user_id,
        activity_id=activity.id,
        label=body.name,
        order=next_order,
    )
    return _hotkey_to_response(hotkey, activity_repo)


@router.delete(
    "/hotkeys/{hotkey_id}",
    status_code=204,
    summary="Удалить hotkey-кнопку",
)
def delete_hotkey(
    hotkey_id: int,
    user_id: int = Depends(get_current_user_id),
    hotkeys_repo: HotkeysRepo = Depends(get_hotkeys_repo),
) -> None:
    """
    Удалить hotkey-кнопку по id.

    :param hotkey_id: Идентификатор hotkey.
    :param user_id: Идентификатор пользователя из сессии.
    :param hotkeys_repo: Репозиторий hotkeys.
    """
    hotkeys = hotkeys_repo.list_by_user(user_id)
    hotkey = next((h for h in hotkeys if h.id == hotkey_id), None)
    if hotkey is None:
        raise HTTPException(status_code=404, detail="Hotkey не найден")
    hotkeys_repo.remove(hotkey_id)


@router.put(
    "/hotkeys/reorder",
    response_model=list[HotkeyResponse],
    summary="Изменить порядок hotkey-кнопок",
)
def reorder_hotkeys(
    body: HotkeyReorderBody,
    user_id: int = Depends(get_current_user_id),
    hotkeys_repo: HotkeysRepo = Depends(get_hotkeys_repo),
    activity_repo: ActivityRepo = Depends(get_activity_repo),
) -> list[HotkeyResponse]:
    """
    Задать новый порядок hotkey: передать список id в нужном порядке.

    :param body: Список hotkey_ids в новом порядке.
    :param user_id: Идентификатор пользователя из сессии.
    :param hotkeys_repo: Репозиторий hotkeys.
    :param activity_repo: Репозиторий активностей.
    :returns: Обновлённый список hotkey (по order).
    """
    hotkeys_repo.reorder(user_id, body.hotkey_ids)
    updated = hotkeys_repo.list_by_user(user_id)
    return [_hotkey_to_response(h, activity_repo) for h in updated]
