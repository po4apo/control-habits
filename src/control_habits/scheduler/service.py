"""Сервис планировщика: выборка pending с блокировкой, отправка через Bot API, mark_sent, ретраи."""

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, cast

import httpx
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.orm import Session

from control_habits.bot_messages.prompts import (
    build_event_end_prompt,
    build_event_start_prompt,
    build_task_prompt,
)
from control_habits.planning_engine.jobs import build_notification_jobs
from control_habits.schedule_model.dto import PlannedItem, PlannedItemType
from control_habits.storage.models import Notification, PlanItem
from control_habits.storage.repositories.notifications import NotificationsRepo
from control_habits.storage.repositories.schedule import ScheduleRepo
from control_habits.storage.repositories.users import UsersRepo

logger = logging.getLogger(__name__)

# Интервал ретраев (секунды): первая попытка сразу, затем 1, 2, 4
RETRY_DELAYS = (0, 1, 2, 4)
MAX_RETRIES = len(RETRY_DELAYS)

# Признаки ответа Telegram «пользователь заблокировал бота» — не ретраим
BLOCKED_BOT_PHRASES = ("blocked by the user", "user is deactivated", "bot was blocked")


def _reply_markup_to_api(markup: InlineKeyboardMarkup) -> dict[str, Any]:
    """Привести InlineKeyboardMarkup к виду для Telegram Bot API (JSON)."""
    if hasattr(markup, "model_dump"):
        return markup.model_dump(exclude_none=True)
    return {}


def _is_blocked_error(response: httpx.Response) -> bool:
    """
    Проверить, что ошибка Telegram означает «пользователь заблокировал бота».

    :param response: Ответ HTTP от Bot API.
    :returns: True, если не нужно ретраить (блокировка/деактивация).
    """
    if response.status_code != 403:
        return False
    try:
        body = response.json()
        desc = (body.get("description") or "").lower()
        return any(phrase in desc for phrase in BLOCKED_BOT_PHRASES)
    except Exception:
        return False


def _send_message_sync(
    bot_token: str,
    chat_id: int,
    text: str,
    reply_markup: dict[str, Any] | None,
) -> httpx.Response:
    """
    Отправить сообщение в Telegram через Bot API (синхронно).

    :param bot_token: Токен бота.
    :param chat_id: Telegram chat_id (user id).
    :param text: Текст сообщения.
    :param reply_markup: reply_markup для sendMessage (dict) или None.
    :returns: Ответ HTTP.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    with httpx.Client(timeout=30.0) as client:
        return client.post(url, json=payload)


def _notification_type_to_planned_type(notification_type: str) -> PlannedItemType:
    """Маппинг notification.type -> PlannedItem.type (task_prompt -> task)."""
    if notification_type == "task_prompt":
        return "task"
    if notification_type in ("event_start", "event_end"):
        return cast(PlannedItemType, notification_type)
    return "task"


class PushSchedulerService:
    """
    Планировщик отправки пушей: раз в N секунд выборка get_pending_locked,
    формирование текста/клавиатуры через bot_messages, отправка в Telegram, mark_sent.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        bot_token: str,
        interval_seconds: int = 60,
    ) -> None:
        """
        :param session_factory: Фабрика сессий SQLAlchemy (каждый тик — своя сессия).
        :param bot_token: Токен бота Telegram.
        :param interval_seconds: Интервал запуска тика (секунды).
        """
        self._session_factory = session_factory
        self._bot_token = bot_token
        self._interval_seconds = interval_seconds

    def run_tick(self) -> None:
        """
        Один тик: заполнение очереди уведомлений на сегодня, выборка pending, отправка, mark_sent.

        Сначала для всех пользователей с шаблоном расписания строятся задачи на сегодня
        (build_notification_jobs) и добавляются в notifications с игнорированием дубликатов.
        Затем выборка pending с FOR UPDATE SKIP LOCKED, отправка каждого пуша, mark_sent.
        При «user blocked bot» — не ретраим, логируем, помечаем отправленным.
        """
        now = datetime.now(timezone.utc)
        session = self._session_factory()
        try:
            notifications_repo = NotificationsRepo(session)
            users_repo = UsersRepo(session)
            schedule_repo = ScheduleRepo(session)
            today_utc = now.date()
            for user_id in schedule_repo.list_user_ids_with_templates():
                jobs = build_notification_jobs(
                    user_id,
                    today_utc,
                    schedule_repo=schedule_repo,
                    users_repo=users_repo,
                )
                if not jobs:
                    continue
                records = [
                    {
                        "user_id": user_id,
                        "plan_item_id": j.plan_item_id,
                        "planned_at": j.planned_at,
                        "type": j.type,
                        "idempotency_key": j.idempotency_key,
                    }
                    for j in jobs
                ]
                notifications_repo.create_many_ignore_duplicates(records)
            pending = notifications_repo.get_pending_locked(now)
            for notification in pending:
                self._process_one(
                    session=session,
                    notification=notification,
                    notifications_repo=notifications_repo,
                    users_repo=users_repo,
                    now=now,
                )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Ошибка в тике планировщика пушей")
            raise
        finally:
            session.close()

    def _process_one(
        self,
        session: Session,
        notification: Notification,
        notifications_repo: NotificationsRepo,
        users_repo: UsersRepo,
        now: datetime,
    ) -> None:
        """
        Отправить один пуш и при успехе (или «blocked») пометить sent_at.

        :param session: Текущая сессия БД.
        :param notification: Уведомление к отправке.
        :param notifications_repo: Репозиторий уведомлений.
        :param users_repo: Репозиторий пользователей.
        :param now: Время отправки (UTC).
        """
        user = users_repo.get_by_id(notification.user_id)
        if user is None:
            logger.warning("Уведомление %s: пользователь не найден", notification.id)
            return
        plan_item = session.get(PlanItem, notification.plan_item_id)
        if plan_item is None:
            logger.warning("Уведомление %s: элемент плана не найден", notification.id)
            return

        planned_type = _notification_type_to_planned_type(notification.type)
        planned_item = PlannedItem(
            plan_item_id=notification.plan_item_id,
            date=notification.planned_at.date(),
            planned_at=notification.planned_at,
            type=planned_type,
        )
        title = plan_item.title
        notification_id = notification.id

        if notification.type == "task_prompt":
            text, reply_markup = build_task_prompt(
                planned_item, title=title, notification_id=notification_id
            )
        elif notification.type == "event_start":
            text, reply_markup = build_event_start_prompt(
                planned_item, title=title, notification_id=notification_id
            )
        elif notification.type == "event_end":
            text, reply_markup = build_event_end_prompt(
                planned_item, title=title, notification_id=notification_id
            )
        else:
            logger.warning("Уведомление %s: неизвестный type=%s", notification.id, notification.type)
            return

        reply_markup_dict = _reply_markup_to_api(reply_markup)

        for attempt in range(MAX_RETRIES):
            if attempt > 0:
                time.sleep(RETRY_DELAYS[attempt])
            try:
                response = _send_message_sync(
                    self._bot_token,
                    chat_id=user.telegram_user_id,
                    text=text,
                    reply_markup=reply_markup_dict or None,
                )
            except httpx.HTTPError as e:
                logger.warning(
                    "Уведомление %s, попытка %s: ошибка HTTP %s",
                    notification.id,
                    attempt + 1,
                    e,
                )
                continue
            if response.status_code == 200:
                notifications_repo.mark_sent(notification.id, now)
                return
            if _is_blocked_error(response):
                logger.info(
                    "Уведомление %s: пользователь заблокировал бота (chat_id=%s), не ретраим",
                    notification.id,
                    user.telegram_user_id,
                )
                notifications_repo.mark_sent(notification.id, now)
                return
            logger.warning(
                "Уведомление %s, попытка %s: Telegram API %s %s",
                notification.id,
                attempt + 1,
                response.status_code,
                response.text[:200],
            )
        logger.error(
            "Уведомление %s: исчерпаны ретраи, отправка не выполнена",
            notification.id,
        )
