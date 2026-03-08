"""Обработка callback от кнопок пушей: идемпотентность, LogEntry, обновление сообщения, answer_callback_query."""

from collections.abc import Callable
from datetime import datetime, timezone

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Filter
from aiogram.types import CallbackQuery
from sqlalchemy.orm import Session

from control_habits.bot_messages.types import (
    CALLBACK_PREFIX_EVENT_ENDED,
    CALLBACK_PREFIX_EVENT_NOT_STARTED,
    CALLBACK_PREFIX_EVENT_SKIPPED,
    CALLBACK_PREFIX_EVENT_STARTED,
    CALLBACK_PREFIX_TASK_DONE,
    CALLBACK_PREFIX_TASK_NOT_DONE,
    CALLBACK_PREFIX_TASK_SKIP,
)
from control_habits.storage.repositories.logs import LogsRepo
from control_habits.storage.repositories.notifications import NotificationsRepo
from control_habits.storage.repositories.users import UsersRepo

# Префиксы callback_data, относящиеся к ответам на пуши (для фильтрации)
PUSH_CALLBACK_PREFIXES = (
    CALLBACK_PREFIX_TASK_DONE,
    CALLBACK_PREFIX_TASK_NOT_DONE,
    CALLBACK_PREFIX_TASK_SKIP,
    CALLBACK_PREFIX_EVENT_STARTED,
    CALLBACK_PREFIX_EVENT_NOT_STARTED,
    CALLBACK_PREFIX_EVENT_ENDED,
    CALLBACK_PREFIX_EVENT_SKIPPED,
)

# Маппинг префикса кнопки → action для LogEntry (domain-model: task_done, event_started и т.д.)
PREFIX_TO_ACTION: dict[str, str] = {
    CALLBACK_PREFIX_TASK_DONE: "task_done",
    CALLBACK_PREFIX_TASK_NOT_DONE: "task_not_done",
    CALLBACK_PREFIX_TASK_SKIP: "task_skipped",
    CALLBACK_PREFIX_EVENT_STARTED: "event_started",
    CALLBACK_PREFIX_EVENT_NOT_STARTED: "event_not_started",
    CALLBACK_PREFIX_EVENT_ENDED: "event_ended",
    CALLBACK_PREFIX_EVENT_SKIPPED: "event_skipped",
}

MSG_ALREADY_COUNTED = "Уже учтено."
MSG_COUNTED = "Учтено."


class PushCallbackFilter(Filter):
    """Фильтр: callback_data относится к ответу на пуш (префикс из PUSH_CALLBACK_PREFIXES)."""

    async def __call__(self, callback: CallbackQuery) -> bool:
        if not callback.data:
            return False
        return any(
            callback.data.startswith(prefix) for prefix in PUSH_CALLBACK_PREFIXES
        )


def _parse_push_callback_data(data: str) -> tuple[str, int] | None:
    """
    Разобрать callback_data ответа на пуш: префикс + notification_id.

    :param data: Строка callback_data (например td_123).
    :returns: (action для LogEntry, notification_id) или None при неверном формате.
    """
    for prefix in PUSH_CALLBACK_PREFIXES:
        if data.startswith(prefix):
            suffix = data[len(prefix) :].strip()
            if not suffix:
                return None
            try:
                notification_id = int(suffix)
            except ValueError:
                return None
            action = PREFIX_TO_ACTION.get(prefix)
            if action is None:
                return None
            return (action, notification_id)
    return None


def setup_push_callback_handler(
    router: Router,
    get_deps: Callable[
        [],
        tuple[UsersRepo, LogsRepo, NotificationsRepo, Session],
    ],
) -> None:
    """
    Регистрирует обработчик callback_query для кнопок ответа на пуши.

    Логика: разбор callback_data (тип + notification_id), проверка идемпотентности
    по ключу (notification_id), при отсутствии записи — создание LogEntry и обновление
    сообщения; всегда вызывается answer_callback_query.

    :param router: Роутер aiogram.
    :param get_deps: Функция, возвращающая (UsersRepo, LogsRepo, NotificationsRepo, Session).
                    После использования вызывающий должен commit/rollback и close сессии.
    """

    @router.callback_query(PushCallbackFilter())
    async def on_push_callback(callback: CallbackQuery) -> None:
        parsed = _parse_push_callback_data(callback.data or "")
        if parsed is None:
            await callback.answer("Ошибка формата кнопки.", show_alert=True)
            return

        action, notification_id = parsed
        telegram_user_id = callback.from_user.id if callback.from_user else 0
        idempotency_key = str(notification_id)

        users_repo, logs_repo, notifications_repo, session = get_deps()
        try:
            user = users_repo.get_by_telegram_id(telegram_user_id)
            if user is None:
                await callback.answer("Сначала привяжи аккаунт через /start.", show_alert=True)
                return

            already_logged = logs_repo.exists_by_idempotency_key(idempotency_key)

            if already_logged:
                await callback.answer(MSG_ALREADY_COUNTED, show_alert=False)
                await _edit_message_to_already_counted(callback)
                return

            notification = notifications_repo.get_by_id(notification_id)
            if notification is None or notification.user_id != user.id:
                await callback.answer("Уведомление не найдено.", show_alert=True)
                return

            now = datetime.now(timezone.utc)
            logs_repo.add(
                user_id=user.id,
                responded_at=now,
                action=action,
                plan_item_id=notification.plan_item_id,
                planned_at=notification.planned_at,
                payload={"idempotency_key": idempotency_key, "notification_id": notification_id},
            )
            session.commit()

            await callback.answer(MSG_COUNTED, show_alert=False)
            await _edit_message_to_counted(callback)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


async def _edit_message_to_counted(callback: CallbackQuery) -> None:
    """Обновить сообщение: убрать кнопки, добавить подпись «Учтено»."""
    if not callback.message or not callback.message.text:
        return
    new_text = callback.message.text.rstrip()
    if not new_text.endswith(MSG_COUNTED):
        new_text = f"{new_text}\n{MSG_COUNTED}"
    try:
        await callback.message.edit_text(new_text, reply_markup=None)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def _edit_message_to_already_counted(callback: CallbackQuery) -> None:
    """При повторном нажатии при необходимости отредактировать сообщение на «Уже учтено»."""
    if not callback.message or not callback.message.text:
        return
    if MSG_ALREADY_COUNTED in callback.message.text:
        return
    new_text = callback.message.text.rstrip()
    if new_text.endswith(MSG_COUNTED):
        new_text = new_text[: -len(MSG_COUNTED)].rstrip()
    new_text = f"{new_text}\n{MSG_ALREADY_COUNTED}"
    try:
        await callback.message.edit_text(new_text, reply_markup=None)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
