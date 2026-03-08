"""Сборка текста и inline-кнопок для пушей по расписанию (task / event_start / event_end)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from control_habits.bot_messages.types import (
    CALLBACK_PREFIX_EVENT_ENDED,
    CALLBACK_PREFIX_EVENT_NOT_STARTED,
    CALLBACK_PREFIX_EVENT_SKIPPED,
    CALLBACK_PREFIX_EVENT_STARTED,
    CALLBACK_PREFIX_TASK_DONE,
    CALLBACK_PREFIX_TASK_NOT_DONE,
    CALLBACK_PREFIX_TASK_SKIP,
)
from control_habits.schedule_model.dto import PlannedItem

# Лимит callback_data в Telegram (байты)
CALLBACK_DATA_MAX_BYTES = 64


def _callback_fits(data: str) -> bool:
    """Проверка, что callback_data укладывается в лимит Telegram."""
    return len(data.encode("utf-8")) <= CALLBACK_DATA_MAX_BYTES


def _button(text: str, callback_data: str) -> InlineKeyboardButton | None:
    """Кнопка, если callback_data в лимите; иначе None."""
    if not _callback_fits(callback_data):
        return None
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def build_task_prompt(
    task_planned: PlannedItem,
    *,
    title: str,
    notification_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Текст и кнопки для пуша «Сделал [title]?» (задача).

    :param task_planned: Элемент плана типа task (для контекста; текст берётся из title).
    :param title: Название дела (из PlanItem.title).
    :param notification_id: Идентификатор уведомления (для callback_data и идемпотентности в bot_handlers).
    :returns: (текст сообщения, InlineKeyboardMarkup с кнопками Сделал / Не сделал / Пропустить).
    """
    if task_planned.type != "task":
        raise ValueError("task_planned.type должен быть 'task'")
    text = f"Сделал {title}?"
    parts = [
        _button("Сделал", f"{CALLBACK_PREFIX_TASK_DONE}{notification_id}"),
        _button("Не сделал", f"{CALLBACK_PREFIX_TASK_NOT_DONE}{notification_id}"),
        _button("Пропустить", f"{CALLBACK_PREFIX_TASK_SKIP}{notification_id}"),
    ]
    buttons = [[b] for b in parts if b is not None]
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


def build_event_start_prompt(
    event_planned: PlannedItem,
    *,
    title: str,
    notification_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Текст и кнопки для пуша «Начал [title]?» (начало события).

    :param event_planned: Элемент плана типа event_start.
    :param title: Название события (из PlanItem.title).
    :param notification_id: Идентификатор уведомления для callback_data.
    :returns: (текст сообщения, InlineKeyboardMarkup с кнопками Начал / Не начал).
    """
    if event_planned.type != "event_start":
        raise ValueError("event_planned.type должен быть 'event_start'")
    text = f"Начал {title}?"
    parts = [
        _button("Начал", f"{CALLBACK_PREFIX_EVENT_STARTED}{notification_id}"),
        _button("Не начал", f"{CALLBACK_PREFIX_EVENT_NOT_STARTED}{notification_id}"),
    ]
    buttons = [[b] for b in parts if b is not None]
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


def build_event_end_prompt(
    event_planned: PlannedItem,
    *,
    title: str,
    notification_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Текст и кнопки для пуша «Закончил [title]?» (конец события).

    :param event_planned: Элемент плана типа event_end.
    :param title: Название события (из PlanItem.title).
    :param notification_id: Идентификатор уведомления для callback_data.
    :returns: (текст сообщения, InlineKeyboardMarkup с кнопками Закончил / Пропустил).
    """
    if event_planned.type != "event_end":
        raise ValueError("event_planned.type должен быть 'event_end'")
    text = f"Закончил {title}?"
    parts = [
        _button("Закончил", f"{CALLBACK_PREFIX_EVENT_ENDED}{notification_id}"),
        _button("Пропустил", f"{CALLBACK_PREFIX_EVENT_SKIPPED}{notification_id}"),
    ]
    buttons = [[b] for b in parts if b is not None]
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)
