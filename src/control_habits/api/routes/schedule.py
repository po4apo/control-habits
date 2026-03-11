"""Эндпоинты CRUD шаблона расписания и элементов плана (TaskItem, EventItem)."""

from datetime import time

from fastapi import APIRouter, Depends, HTTPException

from control_habits.api.deps import (
    get_activity_repo,
    get_current_user_id,
    get_schedule_repo,
)
from control_habits.api.schemas.schedule import (
    PlanItemCreate,
    PlanItemResponse,
    PlanItemUpdate,
    ScheduleTemplateCreate,
    ScheduleTemplateResponse,
    ScheduleTemplateUpdate,
)
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.schedule import ScheduleRepo, _UNSET


def _parse_time(s: str) -> time:
    """Строка HH:MM или HH:MM:SS в time."""
    parts = s.strip().split(":")
    if len(parts) == 2:
        return time(int(parts[0]), int(parts[1]))
    if len(parts) == 3:
        return time(int(parts[0]), int(parts[1]), int(parts[2]))
    raise ValueError("HH:MM или HH:MM:SS")


router = APIRouter(prefix="/schedule", tags=["schedule"])


# --- Шаблон ---


@router.get(
    "/template",
    response_model=ScheduleTemplateResponse | None,
    summary="Получить шаблон расписания",
    description="В MVP у пользователя один шаблон — возвращается первый по id.",
)
def get_template(
    user_id: int = Depends(get_current_user_id),
    schedule_repo: ScheduleRepo = Depends(get_schedule_repo),
) -> ScheduleTemplateResponse | None:
    """
    Получить шаблон расписания текущего пользователя.

    :param user_id: Идентификатор пользователя из сессии.
    :param schedule_repo: Репозиторий расписаний.
    :returns: Шаблон или None, если ещё не создан.
    """
    template = schedule_repo.get_template(user_id)
    if template is None:
        return None
    return ScheduleTemplateResponse.model_validate(template)


@router.post(
    "/template",
    response_model=ScheduleTemplateResponse,
    status_code=201,
    summary="Создать шаблон расписания",
)
def create_template(
    body: ScheduleTemplateCreate,
    user_id: int = Depends(get_current_user_id),
    schedule_repo: ScheduleRepo = Depends(get_schedule_repo),
) -> ScheduleTemplateResponse:
    """
    Создать шаблон расписания.

    :param body: Название шаблона.
    :param user_id: Идентификатор пользователя из сессии.
    :param schedule_repo: Репозиторий расписаний.
    :returns: Созданный шаблон.
    """
    template = schedule_repo.create_template(user_id=user_id, name=body.name)
    return ScheduleTemplateResponse.model_validate(template)


@router.put(
    "/template/{template_id}",
    response_model=ScheduleTemplateResponse,
    summary="Обновить шаблон расписания",
)
def update_template(
    template_id: int,
    body: ScheduleTemplateUpdate,
    user_id: int = Depends(get_current_user_id),
    schedule_repo: ScheduleRepo = Depends(get_schedule_repo),
) -> ScheduleTemplateResponse:
    """
    Обновить название шаблона.

    :param template_id: Идентификатор шаблона.
    :param body: Новое название.
    :param user_id: Идентификатор пользователя из сессии.
    :param schedule_repo: Репозиторий расписаний.
    :returns: Обновлённый шаблон.
    """
    template = schedule_repo.get_template_by_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    if template.user_id != user_id:
        raise HTTPException(status_code=403, detail="Нет доступа к шаблону")
    schedule_repo.update_template(template_id, name=body.name)
    schedule_repo._session.refresh(template)
    return ScheduleTemplateResponse.model_validate(template)


@router.delete(
    "/template/{template_id}",
    status_code=204,
    summary="Удалить шаблон расписания",
)
def delete_template(
    template_id: int,
    user_id: int = Depends(get_current_user_id),
    schedule_repo: ScheduleRepo = Depends(get_schedule_repo),
) -> None:
    """
    Удалить шаблон и все его элементы плана.

    :param template_id: Идентификатор шаблона.
    :param user_id: Идентификатор пользователя из сессии.
    :param schedule_repo: Репозиторий расписаний.
    """
    template = schedule_repo.get_template_by_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    if template.user_id != user_id:
        raise HTTPException(status_code=403, detail="Нет доступа к шаблону")
    schedule_repo.delete_template(template_id)


# --- Элементы плана ---


@router.get(
    "/template/{template_id}/items",
    response_model=list[PlanItemResponse],
    summary="Список элементов плана шаблона",
)
def list_plan_items(
    template_id: int,
    user_id: int = Depends(get_current_user_id),
    schedule_repo: ScheduleRepo = Depends(get_schedule_repo),
) -> list[PlanItemResponse]:
    """
    Получить все элементы плана шаблона (TaskItem и EventItem).

    :param template_id: Идентификатор шаблона.
    :param user_id: Идентификатор пользователя из сессии.
    :param schedule_repo: Репозиторий расписаний.
    :returns: Список элементов плана.
    """
    template = schedule_repo.get_template_by_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    if template.user_id != user_id:
        raise HTTPException(status_code=403, detail="Нет доступа к шаблону")
    items = schedule_repo.get_plan_items(template_id)
    return [PlanItemResponse.from_orm_item(it) for it in items]


@router.post(
    "/template/{template_id}/items",
    response_model=PlanItemResponse,
    status_code=201,
    summary="Добавить элемент плана",
)
def create_plan_item(
    template_id: int,
    body: PlanItemCreate,
    user_id: int = Depends(get_current_user_id),
    schedule_repo: ScheduleRepo = Depends(get_schedule_repo),
    activity_repo: ActivityRepo = Depends(get_activity_repo),
) -> PlanItemResponse:
    """
    Создать элемент плана (дело или событие).

    Время в теле — в локальном времени пользователя (день); в БД хранится как время дня.
    Для событий title берётся из activity, если не передан.

    :param template_id: Идентификатор шаблона.
    :param body: Поля элемента (kind, title, start_time, end_time, days_of_week, activity_id).
    :param user_id: Идентификатор пользователя из сессии.
    :param schedule_repo: Репозиторий расписаний.
    :param activity_repo: Репозиторий активностей.
    :returns: Созданный элемент плана.
    """
    template = schedule_repo.get_template_by_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    if template.user_id != user_id:
        raise HTTPException(status_code=403, detail="Нет доступа к шаблону")
    start = _parse_time(body.start_time)
    end = _parse_time(body.end_time)
    title = (body.title or "").strip() or None
    if body.kind == "event" and not title and body.activity_id is not None:
        activity = activity_repo.get_by_id(body.activity_id)
        if activity is None or activity.user_id != user_id:
            raise HTTPException(status_code=404, detail="Активность не найдена")
        title = activity.name
    if not title:
        raise HTTPException(status_code=400, detail="Укажите название или активность")
    item = schedule_repo.create_plan_item(
        template_id=template_id,
        kind=body.kind,
        title=title,
        start_time=start,
        end_time=end,
        days_of_week=body.days_of_week,
        activity_id=body.activity_id,
    )
    return PlanItemResponse.from_orm_item(item)


@router.get(
    "/plan-items/{plan_item_id}",
    response_model=PlanItemResponse,
    summary="Получить элемент плана по id",
)
def get_plan_item(
    plan_item_id: int,
    user_id: int = Depends(get_current_user_id),
    schedule_repo: ScheduleRepo = Depends(get_schedule_repo),
) -> PlanItemResponse:
    """
    Получить один элемент плана.

    :param plan_item_id: Идентификатор элемента плана.
    :param user_id: Идентификатор пользователя из сессии.
    :param schedule_repo: Репозиторий расписаний.
    :returns: Элемент плана.
    """
    item = schedule_repo.get_plan_item(plan_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Элемент плана не найден")
    template = schedule_repo.get_template_by_id(item.template_id)
    if template is None or template.user_id != user_id:
        raise HTTPException(status_code=403, detail="Нет доступа к элементу плана")
    return PlanItemResponse.from_orm_item(item)


@router.patch(
    "/plan-items/{plan_item_id}",
    response_model=PlanItemResponse,
    summary="Обновить элемент плана",
)
def update_plan_item(
    plan_item_id: int,
    body: PlanItemUpdate,
    user_id: int = Depends(get_current_user_id),
    schedule_repo: ScheduleRepo = Depends(get_schedule_repo),
    activity_repo: ActivityRepo = Depends(get_activity_repo),
) -> PlanItemResponse:
    """
    Обновить элемент плана (частичное обновление).
    Для событий при смене activity_id title обновляется из новой активности.

    :param plan_item_id: Идентификатор элемента плана.
    :param body: Поля для обновления (все опциональны).
    :param user_id: Идентификатор пользователя из сессии.
    :param schedule_repo: Репозиторий расписаний.
    :param activity_repo: Репозиторий активностей.
    :returns: Обновлённый элемент плана.
    """
    item = schedule_repo.get_plan_item(plan_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Элемент плана не найден")
    template = schedule_repo.get_template_by_id(item.template_id)
    if template is None or template.user_id != user_id:
        raise HTTPException(status_code=403, detail="Нет доступа к элементу плана")
    updates = body.model_dump(exclude_unset=True)
    if "start_time" in updates:
        updates["start_time"] = _parse_time(updates["start_time"])
    if "end_time" in updates:
        updates["end_time"] = _parse_time(updates["end_time"])
    activity_id = updates.pop("activity_id", _UNSET)
    if activity_id is None and item.kind == "event":
        raise HTTPException(
            status_code=400,
            detail="Для события activity_id обязателен — без него бот не сможет отслеживать паузу и трекинг",
        )
    title = updates.get("title")
    if item.kind == "event":
        updates.pop("title", None)
        if activity_id is not _UNSET and activity_id is not None:
            activity = activity_repo.get_by_id(activity_id)
            if activity is not None and activity.user_id == user_id:
                title = activity.name
    schedule_repo.update_plan_item(
        plan_item_id,
        title=title,
        start_time=updates.get("start_time"),
        end_time=updates.get("end_time"),
        days_of_week=updates.get("days_of_week"),
        activity_id=activity_id,
    )
    schedule_repo._session.refresh(item)
    return PlanItemResponse.from_orm_item(item)


@router.delete(
    "/plan-items/{plan_item_id}",
    status_code=204,
    summary="Удалить элемент плана",
)
def delete_plan_item(
    plan_item_id: int,
    user_id: int = Depends(get_current_user_id),
    schedule_repo: ScheduleRepo = Depends(get_schedule_repo),
) -> None:
    """
    Удалить элемент плана.

    :param plan_item_id: Идентификатор элемента плана.
    :param user_id: Идентификатор пользователя из сессии.
    :param schedule_repo: Репозиторий расписаний.
    """
    item = schedule_repo.get_plan_item(plan_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Элемент плана не найден")
    template = schedule_repo.get_template_by_id(item.template_id)
    if template is None or template.user_id != user_id:
        raise HTTPException(status_code=403, detail="Нет доступа к элементу плана")
    schedule_repo.delete_plan_item(plan_item_id)
