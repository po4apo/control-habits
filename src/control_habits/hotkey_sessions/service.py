"""Старт/стоп сессий и список активных. Все времена в UTC."""

from datetime import datetime

from control_habits.storage.models import ActiveSession
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.sessions import SessionsRepo


def start_session(
    sessions_repo: SessionsRepo,
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
    sessions_repo: SessionsRepo,
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
    sessions_repo: SessionsRepo,
    activity_repo: ActivityRepo,
    user_id: int,
) -> list[ActiveSession]:
    """
    Все активные сессии пользователя (ended_at IS NULL) с подгрузкой названий активностей.

    У каждого элемента в списке установлен атрибут activity_name (str | None).

    :param sessions_repo: Репозиторий сессий.
    :param activity_repo: Репозиторий активностей (для подгрузки названий).
    :param user_id: Идентификатор пользователя.
    :returns: Список ActiveSession, упорядоченный по started_at.
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
