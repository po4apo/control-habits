"""Старт/стоп сессий и список активных. Все времена в UTC."""

from datetime import datetime

from control_habits.storage.models import TimeSegment
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.sessions import TimeSegmentRepo


def start_session(
    sessions_repo: TimeSegmentRepo,
    user_id: int,
    activity_id: int,
    now: datetime,
) -> int:
    """
    Создать активную сессию или вернуть id существующей (идемпотентный повторный старт).

    Инвариант: не более одной активной сессии на (user_id, activity_id).

    :param sessions_repo: Репозиторий сессий.
    :param user_id: Идентификатор пользователя.
    :param activity_id: Идентификатор активности.
    :param now: Текущее время (UTC), записывается как started_at при создании.
    :returns: Идентификатор сессии (новой или уже активной).
    """
    existing = sessions_repo.get_active(user_id, activity_id)
    if existing is not None:
        return existing.id
    session = sessions_repo.create(user_id, activity_id, now)
    return session.id


def stop_session(
    sessions_repo: TimeSegmentRepo,
    user_id: int,
    activity_id: int,
    now: datetime,
) -> float | None:
    """
    Завершить активную сессию: выставить ended_at = now.

    Идемпотентно: если активной сессии нет, возвращается None без ошибки.

    :param sessions_repo: Репозиторий сессий.
    :param user_id: Идентификатор пользователя.
    :param activity_id: Идентификатор активности.
    :param now: Время окончания (UTC).
    :returns: Длительность сессии в секундах или None, если активной сессии не было.
    """
    session = sessions_repo.get_active(user_id, activity_id)
    if session is None:
        return None
    duration_seconds = (now - session.started_at).total_seconds()
    sessions_repo.close(session.id, now)
    return duration_seconds


def list_active_sessions(
    sessions_repo: TimeSegmentRepo,
    activity_repo: ActivityRepo,
    user_id: int,
) -> list[TimeSegment]:
    """
    Все активные сессии пользователя (ended_at IS NULL) с подгрузкой названий активностей.

    У каждого элемента в списке установлен атрибут activity_name (str | None).

    :param sessions_repo: Репозиторий сессий.
    :param activity_repo: Репозиторий активностей (для подгрузки названий).
    :param user_id: Идентификатор пользователя.
    :returns: Список TimeSegment, упорядоченный по started_at.
    """
    sessions = sessions_repo.list_active(user_id)
    for session in sessions:
        activity = activity_repo.get_by_id(session.activity_id)
        setattr(
            session,
            "activity_name",
            activity.name if activity is not None else None,
        )
    return sessions


def pause_session(
    sessions_repo: TimeSegmentRepo,
    user_id: int,
    activity_id: int,
    now: datetime,
    plan_item_id: int | None = None,
) -> float | None:
    """
    Поставить на паузу: закрыть открытый отрезок.

    :param sessions_repo: Репозиторий отрезков.
    :param user_id: Идентификатор пользователя.
    :param activity_id: Идентификатор активности.
    :param now: Время паузы (UTC).
    :param plan_item_id: Опционально — для запланированного события.
    :returns: Длительность закрытого отрезка в секундах или None.
    """
    if plan_item_id is not None:
        segment = sessions_repo.get_open_by_plan_item(user_id, plan_item_id)
    else:
        segment = sessions_repo.get_open(user_id, activity_id, None)
    if segment is None:
        return None
    duration = (now - segment.started_at).total_seconds()
    sessions_repo.close(segment.id, now)
    return duration


def resume_session(
    sessions_repo: TimeSegmentRepo,
    user_id: int,
    activity_id: int,
    now: datetime,
    plan_item_id: int | None = None,
) -> int:
    """
    Продолжить: создать новый отрезок.

    :param sessions_repo: Репозиторий отрезков.
    :param user_id: Идентификатор пользователя.
    :param activity_id: Идентификатор активности.
    :param now: Время возобновления (UTC).
    :param plan_item_id: Опционально — для запланированного события.
    :returns: Идентификатор нового отрезка.
    """
    segment = sessions_repo.create(
        user_id=user_id,
        activity_id=activity_id,
        started_at=now,
        plan_item_id=plan_item_id,
    )
    return segment.id
