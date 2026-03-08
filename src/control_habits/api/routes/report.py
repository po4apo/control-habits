"""Эндпоинт отчёта за день."""

from datetime import date

from fastapi import APIRouter, Depends, Query

from control_habits.api.deps import (
    get_activity_repo,
    get_current_user_id,
    get_logs_repo,
    get_schedule_repo,
    get_sessions_repo,
    get_users_repo,
)
from control_habits.api.schemas.report import (
    AnswerFactResponse,
    DailyReportResponse,
    PlannedItemResponse,
    SessionIntervalResponse,
)
from control_habits.reporting.service import get_daily_report
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.logs import LogsRepo
from control_habits.storage.repositories.schedule import ScheduleRepo
from control_habits.storage.repositories.sessions import SessionsRepo
from control_habits.storage.repositories.users import UsersRepo

router = APIRouter(prefix="/report", tags=["report"])


def _time_str(t) -> str:
    """Сериализация time в HH:MM."""
    return t.strftime("%H:%M") if t else ""


@router.get(
    "/daily",
    response_model=DailyReportResponse,
    summary="Отчёт за день",
    description="Список запланированного, фактов ответов и интервалов сессий за указанную дату (день в локальном времени пользователя).",
)
def get_daily_report_endpoint(
    date_param: date = Query(..., alias="date", description="Дата в формате YYYY-MM-DD (локальный день пользователя)"),
    user_id: int = Depends(get_current_user_id),
    schedule_repo: ScheduleRepo = Depends(get_schedule_repo),
    users_repo: UsersRepo = Depends(get_users_repo),
    logs_repo: LogsRepo = Depends(get_logs_repo),
    sessions_repo: SessionsRepo = Depends(get_sessions_repo),
    activity_repo: ActivityRepo = Depends(get_activity_repo),
) -> DailyReportResponse:
    """
    Получить отчёт за один календарный день.

    user_id берётся из текущей привязанной веб-сессии. Дата интерпретируется
    как день в часовом поясе пользователя.

    :param date_param: Календарная дата (локальный день).
    :param user_id: Идентификатор пользователя из сессии.
    :param schedule_repo: Репозиторий расписаний.
    :param users_repo: Репозиторий пользователей.
    :param logs_repo: Репозиторий логов.
    :param sessions_repo: Репозиторий сессий.
    :returns: Отчёт: planned, answers, intervals.
    """
    report = get_daily_report(
        user_id,
        date_param,
        schedule_repo=schedule_repo,
        users_repo=users_repo,
        logs_repo=logs_repo,
        sessions_repo=sessions_repo,
    )
    plan_items_by_id: dict[int, tuple[str, str, str]] = {}
    template = schedule_repo.get_template(user_id)
    if template is not None:
        for it in schedule_repo.get_plan_items(template.id):
            plan_items_by_id[it.id] = (
                it.title,
                _time_str(it.start_time),
                _time_str(it.end_time),
            )
    activity_names: dict[int, str] = {}
    for i in report.intervals:
        if i.activity_id not in activity_names:
            a = activity_repo.get_by_id(i.activity_id)
            activity_names[i.activity_id] = a.name if a else ""
    return DailyReportResponse(
        planned=[
            PlannedItemResponse(
                plan_item_id=p.plan_item_id,
                date=p.date,
                planned_at=p.planned_at,
                type=p.type,
                title=plan_items_by_id.get(p.plan_item_id, ("", "", ""))[0],
                start_time=plan_items_by_id.get(p.plan_item_id, ("", "", ""))[1],
                end_time=plan_items_by_id.get(p.plan_item_id, ("", "", ""))[2],
            )
            for p in report.planned
        ],
        answers=[
            AnswerFactResponse(
                responded_at=a.responded_at,
                action=a.action,
                plan_item_id=a.plan_item_id,
                activity_id=a.activity_id,
                payload=a.payload,
            )
            for a in report.answers
        ],
        intervals=[
            SessionIntervalResponse(
                started_at=i.started_at,
                ended_at=i.ended_at,
                duration_seconds=i.duration_seconds,
                activity_id=i.activity_id,
                activity_name=activity_names.get(i.activity_id, ""),
            )
            for i in report.intervals
        ],
    )
