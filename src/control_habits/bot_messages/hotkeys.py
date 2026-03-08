"""Сборка клавиатур и сообщений для hotkey и активных сессий."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from control_habits.bot_messages.types import (
    CALLBACK_PREFIX_FINISH,
    CALLBACK_PREFIX_HOTKEY,
    ActiveSession,
)
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.hotkeys import HotkeysRepo

# Лимит callback_data в Telegram (байты)
CALLBACK_DATA_MAX_BYTES = 64


def _callback_fits(data: str) -> bool:
    """Проверка, что callback_data укладывается в лимит Telegram."""
    return len(data.encode("utf-8")) <= CALLBACK_DATA_MAX_BYTES


def build_hotkeys_keyboard(
    user_id: int,
    hotkeys_repo: HotkeysRepo,
    activity_repo: ActivityRepo,
) -> InlineKeyboardMarkup:
    """
    Клавиатура с hotkey-кнопками пользователя (подписи из Hotkey.label, callback_data: hk_<activity_id>).

    :param user_id: Идентификатор пользователя.
    :param hotkeys_repo: Репозиторий hotkeys (list_by_user).
    :param activity_repo: Не используется для подписей (подпись берётся из Hotkey.label), оставлен для совместимости с контрактом.
    :returns: InlineKeyboardMarkup с кнопками; callback_data в пределах 64 байт.
    """
    hotkeys = hotkeys_repo.list_by_user(user_id)
    buttons: list[list[InlineKeyboardButton]] = []
    for hk in hotkeys:
        callback_data = f"{CALLBACK_PREFIX_HOTKEY}{hk.activity_id}"
        if not _callback_fits(callback_data):
            continue
        buttons.append(
            [InlineKeyboardButton(text=hk.label, callback_data=callback_data)]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_active_sessions_message(sessions: list[ActiveSession]) -> str:
    """
    Текст списка активных сессий: «Сейчас идёт: YouTube с 14:30; Работа с 09:00».

    :param sessions: Список представлений активных сессий (session_id, activity_name, started_at).
    :returns: Строка для отправки в чат.
    """
    if not sessions:
        return "Нет активных сессий. Нажми кнопку активности, чтобы начать трекать."
    parts = []
    for s in sessions:
        time_str = s.started_at.strftime("%H:%M")
        parts.append(f"{s.activity_name} с {time_str}")
    return "Сейчас идёт: " + "; ".join(parts)


def build_finish_buttons(sessions: list[ActiveSession]) -> InlineKeyboardMarkup:
    """
    Inline-кнопки «Закончить [название]» по одной на каждую сессию; callback_data: fin_<session_id>.

    :param sessions: Список представлений активных сессий.
    :returns: InlineKeyboardMarkup; callback_data в пределах 64 байт.
    """
    buttons: list[list[InlineKeyboardButton]] = []
    for s in sessions:
        callback_data = f"{CALLBACK_PREFIX_FINISH}{s.session_id}"
        if not _callback_fits(callback_data):
            continue
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"Закончить {s.activity_name}",
                    callback_data=callback_data,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
