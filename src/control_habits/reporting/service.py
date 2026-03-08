"""Сервис отчётов за день."""

from datetime import date, datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo

from control_habits.reporting.dto import AnswerFact, DailyReport, SessionInterval
from control_habits.schedule_model.expand import expand_template
from control_habits.storage.models import ActiveSession, LogEntry
from control_habits.storage.repositories.logs import LogsRepo
from control_habits.storage.repositories.schedule import ScheduleRepo
from control_habits.storage.repositories.sessions import SessionsRepo
from control_habits.storage.repositories.users import UsersRepo


def get_daily_report(
    user_id: int,
    target_date: date,
    *,
    schedule_repo: ScheduleRepo,
    users_repo: UsersRepo,
    logs_repo: LogsRepo,
    sessions_repo: SessionsRepo,
) -> DailyReport:
    """
    Собрать отчёт за один календарный день в локальном времени пользователя.

    Дата интерпретируется как день в timezone пользователя. Все времена на выходе — UTC.

    :param user_id: Идентификатор пользователя.
    :param target_date: Календарная дата (день в локальном времени пользователя).
    :param schedule_repo: Репозиторий расписаний (для expand_template).
    :param users_repo: Репозиторий пользователей (timezone).
    :param logs_repo: Репозиторий логов (факты ответов).
    :param sessions_repo: Репозиторий сессий (закрытые сессии за дату).
    :returns: DailyReport: запланированные элементы, факты ответов, интервалы сессий.
    """
    user = users_repo.get_by_id(user_id)
    if user is None:
        return DailyReport(planned=[], answers=[], intervals=[])

    tz = ZoneInfo(user.timezone)
    utc_start = datetime.combine(target_date, time(0, 0), tzinfo=tz).astimezone(
        timezone.utc
    )
    next_day = target_date + timedelta(days=1)
    utc_end = datetime.combine(next_day, time(0, 0), tzinfo=tz).astimezone(
        timezone.utc
    )

    planned = expand_template(
        user_id,
        target_date,
        schedule_repo=schedule_repo,
        users_repo=users_repo,
    )

    log_entries = logs_repo.list_by_user_and_date_range(
        user_id, utc_start, utc_end
    )
    answers = [_log_entry_to_answer_fact(e) for e in log_entries]

    closed_sessions = sessions_repo.list_closed_in_range(
        user_id, utc_start, utc_end
    )
    intervals = [_session_to_interval(s) for s in closed_sessions]

    return DailyReport(planned=planned, answers=answers, intervals=intervals)


def _log_entry_to_answer_fact(entry: LogEntry) -> AnswerFact:
    """
    Преобразовать ORM LogEntry в DTO AnswerFact.

    :param entry: Запись лога из БД.
    :returns: AnswerFact для отчёта.
    """
    return AnswerFact(
        responded_at=entry.responded_at,
        action=entry.action,
        plan_item_id=entry.plan_item_id,
        activity_id=entry.activity_id,
        payload=entry.payload,
    )


def _session_to_interval(session: ActiveSession) -> SessionInterval:
    """
    Преобразовать закрытую сессию в SessionInterval.

    :param session: Закрытая сессия (ended_at не None).
    :returns: SessionInterval с длительностью в секундах.
    """
    assert session.ended_at is not None
    duration = (session.ended_at - session.started_at).total_seconds()
    return SessionInterval(
        started_at=session.started_at,
        ended_at=session.ended_at,
        duration_seconds=duration,
        activity_id=session.activity_id,
    )
