"""Формирование списка задач на отправку уведомлений по развёрнутому плану."""

from datetime import date

from control_habits.planning_engine.dto import NotificationJob, NotificationJobType
from control_habits.schedule_model import expand_template
from control_habits.storage.repositories.notifications import NotificationsRepo
from control_habits.storage.repositories.schedule import ScheduleRepo
from control_habits.storage.repositories.users import UsersRepo


def _planned_type_to_job_type(planned_type: str) -> NotificationJobType:
    """Сопоставление типа PlannedItem типу NotificationJob."""
    if planned_type == "task":
        return "task_prompt"
    if planned_type in ("event_start", "event_end"):
        return planned_type  # type: ignore[return-value]
    raise ValueError(f"Неизвестный тип элемента плана: {planned_type!r}")


def _make_idempotency_key(plan_item_id: int, target_date: date, job_type: str) -> str:
    """Ключ идемпотентности: однозначно один пуш на (plan_item_id, date, type)."""
    return f"{plan_item_id}_{target_date.isoformat()}_{job_type}"


def build_notification_jobs(
    user_id: int,
    target_date: date,
    *,
    schedule_repo: ScheduleRepo,
    users_repo: UsersRepo,
) -> list[NotificationJob]:
    """
    По развёрнутому плану на дату формирует список задач на отправку пушей.

    Использует expand_template; для каждого элемента создаёт NotificationJob
    с planned_at (UTC), type (task_prompt | event_start | event_end),
    plan_item_id, idempotency_key и данными для сообщения (planned_item).

    :param user_id: Идентификатор пользователя.
    :param target_date: Дата, на которую строятся уведомления.
    :param schedule_repo: Репозиторий расписаний.
    :param users_repo: Репозиторий пользователей (timezone).
    :returns: Список NotificationJob, отсортированный по planned_at.
    """
    planned = expand_template(
        user_id,
        target_date,
        schedule_repo=schedule_repo,
        users_repo=users_repo,
    )
    jobs: list[NotificationJob] = []
    for item in planned:
        job_type = _planned_type_to_job_type(item.type)
        idempotency_key = _make_idempotency_key(
            item.plan_item_id, item.date, job_type
        )
        jobs.append(
            NotificationJob(
                planned_at=item.planned_at,
                type=job_type,
                plan_item_id=item.plan_item_id,
                idempotency_key=idempotency_key,
                planned_item=item,
            )
        )
    return jobs


def create_pending_notifications(
    user_id: int,
    jobs: list[NotificationJob],
    notifications_repo: NotificationsRepo,
) -> None:
    """
    Сохранить задачи на отправку в таблицу notifications с sent_at = NULL.

    Планировщик затем выбирает их через get_pending и после отправки вызывает
    mark_sent. При повторном вызове для тех же (user_id, date) дубликаты
    по idempotency_key приведут к ошибке уникальности — создавать записи
    следует один раз (например, при планировании дня).

    :param user_id: Идентификатор пользователя.
    :param jobs: Список NotificationJob из build_notification_jobs.
    :param notifications_repo: Репозиторий уведомлений.
    """
    records = [
        {
            "user_id": user_id,
            "plan_item_id": job.plan_item_id,
            "planned_at": job.planned_at,
            "type": job.type,
            "idempotency_key": job.idempotency_key,
        }
        for job in jobs
    ]
    if records:
        notifications_repo.create_many(records)
