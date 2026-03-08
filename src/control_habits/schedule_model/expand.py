"""Развёртка шаблона расписания на конкретную дату с учётом timezone пользователя."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from control_habits.schedule_model.dto import PlannedItem
from control_habits.storage.repositories.schedule import ScheduleRepo
from control_habits.storage.repositories.users import UsersRepo


def expand_template(
    user_id: int,
    target_date: date,
    *,
    schedule_repo: ScheduleRepo,
    users_repo: UsersRepo,
) -> list[PlannedItem]:
    """
    По шаблону пользователя и дням недели возвращает запланированные элементы на дату в UTC.

    Для каждого элемента плана проверяется, попадает ли target_date в days_of_week (ISO 1–7).
    Время из шаблона (start_time, end_time) интерпретируется в часовом поясе пользователя,
    результат приводится к UTC.

    :param user_id: Идентификатор пользователя.
    :param target_date: Дата, на которую разворачивается план.
    :param schedule_repo: Репозиторий расписаний (шаблон и элементы плана).
    :param users_repo: Репозиторий пользователей (timezone).
    :returns: Список PlannedItem, отсортированный по planned_at (UTC).
    """
    user = users_repo.get_by_id(user_id)
    if user is None:
        return []

    template = schedule_repo.get_template(user_id)
    if template is None:
        return []

    plan_items = schedule_repo.get_plan_items(template.id)
    tz = ZoneInfo(user.timezone)
    result: list[PlannedItem] = []

    weekday = target_date.isoweekday()  # 1–7

    for item in plan_items:
        if weekday not in item.days_of_week:
            continue

        if item.kind == "task":
            local_dt = datetime.combine(target_date, item.start_time, tzinfo=tz)
            utc_dt = local_dt.astimezone(timezone.utc)
            result.append(
                PlannedItem(
                    plan_item_id=item.id,
                    date=target_date,
                    planned_at=utc_dt,
                    type="task",
                )
            )
        elif item.kind == "event":
            local_start = datetime.combine(target_date, item.start_time, tzinfo=tz)
            local_end = datetime.combine(target_date, item.end_time, tzinfo=tz)
            result.append(
                PlannedItem(
                    plan_item_id=item.id,
                    date=target_date,
                    planned_at=local_start.astimezone(timezone.utc),
                    type="event_start",
                )
            )
            result.append(
                PlannedItem(
                    plan_item_id=item.id,
                    date=target_date,
                    planned_at=local_end.astimezone(timezone.utc),
                    type="event_end",
                )
            )

    result.sort(key=lambda p: p.planned_at)
    return result
