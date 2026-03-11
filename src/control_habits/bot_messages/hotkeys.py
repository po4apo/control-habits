"""Сборка клавиатур и сообщений для hotkey и активных сессий."""

from datetime import datetime

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from control_habits.bot_messages.types import (
    CALLBACK_PREFIX_ACTIVE,
    CALLBACK_PREFIX_ACTIVE_DETAIL,
    CALLBACK_PREFIX_ACTIVE_DETAIL_PLAN,
    CALLBACK_PREFIX_BUG_CANCEL,
    CALLBACK_PREFIX_BUG_CONFIRM,
    CALLBACK_PREFIX_FINISH,
    CALLBACK_PREFIX_FINISH_PLAN,
    CALLBACK_PREFIX_HOTKEY,
    CALLBACK_PREFIX_HOTKEYS_MENU,
    ActiveSession,
    CurrentlyOnItem,
)
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.hotkeys import HotkeysRepo

# Лимит callback_data в Telegram (байты)
CALLBACK_DATA_MAX_BYTES = 64


def _callback_fits(data: str) -> bool:
    """Проверка, что callback_data укладывается в лимит Telegram."""
    return len(data.encode("utf-8")) <= CALLBACK_DATA_MAX_BYTES


# Текст кнопки «Что включено» (экран включённых событий)
ACTIVE_BUTTON_LABEL = "Что включено"

# Текст кнопки «Горячие клавиши» (меню горячих кнопок)
HOTKEYS_MENU_LABEL = "Горячие клавиши"

# Текст кнопки отправки баг-репорта в главном меню
BUG_REPORT_BUTTON_LABEL = "Сообщить о баге"


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Главное меню (inline): две кнопки — «Что включено» (act_) и «Горячие клавиши» (hkmenu_).
    Оставлено для обратной совместимости со старыми сообщениями.

    :returns: InlineKeyboardMarkup для главного экрана.
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=ACTIVE_BUTTON_LABEL, callback_data=CALLBACK_PREFIX_ACTIVE)],
        [InlineKeyboardButton(text=HOTKEYS_MENU_LABEL, callback_data=CALLBACK_PREFIX_HOTKEYS_MENU)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_main_menu_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Reply-клавиатура главного меню: «Что включено», «Горячие клавиши», «Сообщить о баге».

    :returns: ReplyKeyboardMarkup для /start и fallback.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=ACTIVE_BUTTON_LABEL)],
            [KeyboardButton(text=HOTKEYS_MENU_LABEL)],
            [KeyboardButton(text=BUG_REPORT_BUTTON_LABEL)],
        ],
        resize_keyboard=True,
    )


def build_active_sessions_buttons(items: list[CurrentlyOnItem]) -> InlineKeyboardMarkup:
    """
    Список «что включено»: по одной inline-кнопке на элемент (hotkey-сессия или запланированное событие).

    Текст: «{title} (с HH:MM)». callback_data: actd_<session_id> или actd_plan_<plan_item_id>.

    :param items: Список элементов (hotkey + запланированные события).
    :returns: InlineKeyboardMarkup; callback_data в пределах 64 байт.
    """
    buttons: list[list[InlineKeyboardButton]] = []
    for it in items:
        time_str = it.started_at.strftime("%H:%M")
        if it.session_id is not None:
            callback_data = f"{CALLBACK_PREFIX_ACTIVE_DETAIL}{it.session_id}"
        else:
            callback_data = f"{CALLBACK_PREFIX_ACTIVE_DETAIL_PLAN}{it.plan_item_id}"
        if not _callback_fits(callback_data):
            continue
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{it.title} (с {time_str})",
                    callback_data=callback_data,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_session_detail_message(activity_name: str, started_at: datetime) -> str:
    """
    Текст детали сессии: «Событие {activity_name} идёт с HH:MM».

    :param activity_name: Название активности.
    :param started_at: Время начала (datetime, будет отформатировано как HH:MM).
    :returns: Строка для сообщения в чат.
    """
    time_str = started_at.strftime("%H:%M")
    return f"Событие {activity_name} идёт с {time_str}."


def build_hotkeys_keyboard(
    user_id: int,
    hotkeys_repo: HotkeysRepo,
    activity_repo: ActivityRepo,
    *,
    include_active_button: bool = False,
    active_activity_ids: set[int] | None = None,
) -> InlineKeyboardMarkup:
    """
    Клавиатура с hotkey-кнопками пользователя (подписи из Hotkey.label, callback_data: hk_<activity_id>).

    Активные сессии помечаются префиксом ``▶`` на кнопке.

    :param user_id: Идентификатор пользователя.
    :param hotkeys_repo: Репозиторий hotkeys (list_by_user).
    :param activity_repo: Не используется для подписей (подпись берётся из Hotkey.label), оставлен для совместимости с контрактом.
    :param include_active_button: Добавить в конец ряд с кнопкой «Что включено» (callback_data act_).
    :param active_activity_ids: Множество activity_id с активными сессиями; помеченные кнопки получают префикс.
    :returns: InlineKeyboardMarkup с кнопками; callback_data в пределах 64 байт.
    """
    active_ids = active_activity_ids or set()
    hotkeys = hotkeys_repo.list_by_user(user_id)
    buttons: list[list[InlineKeyboardButton]] = []
    for hk in hotkeys:
        callback_data = f"{CALLBACK_PREFIX_HOTKEY}{hk.activity_id}"
        if not _callback_fits(callback_data):
            continue
        label = f"▶ {hk.label}" if hk.activity_id in active_ids else hk.label
        buttons.append(
            [InlineKeyboardButton(text=label, callback_data=callback_data)]
        )
    if include_active_button and _callback_fits(CALLBACK_PREFIX_ACTIVE):
        buttons.append(
            [InlineKeyboardButton(text=ACTIVE_BUTTON_LABEL, callback_data=CALLBACK_PREFIX_ACTIVE)]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_active_sessions_message(items: list[CurrentlyOnItem]) -> str:
    """
    Текст списка включённых событий: «Сейчас включено: YouTube с 14:30; Учёба с 09:05».

    :param items: Список элементов (hotkey-сессии и запланированные события).
    :returns: Строка для отправки в чат.
    """
    if not items:
        return "Ничего не включено. Нажми кнопку события, чтобы включить."
    parts = []
    for it in items:
        time_str = it.started_at.strftime("%H:%M")
        parts.append(f"{it.title} с {time_str}")
    return "Сейчас включено: " + "; ".join(parts)


def build_bug_confirm_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    """
    Inline-кнопки «Отправить» и «Отменить» для подтверждения отправки баг-репорта.

    :param draft_id: Id черновика (для callback_data).
    :returns: InlineKeyboardMarkup; callback_data в пределах 64 байт.
    """
    ok_data = f"{CALLBACK_PREFIX_BUG_CONFIRM}{draft_id}"
    cn_data = f"{CALLBACK_PREFIX_BUG_CANCEL}{draft_id}"
    if not _callback_fits(ok_data) or not _callback_fits(cn_data):
        return InlineKeyboardMarkup(inline_keyboard=[])
    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="Отправить", callback_data=ok_data),
            InlineKeyboardButton(text="Отменить", callback_data=cn_data),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_finish_buttons(items: list[CurrentlyOnItem]) -> InlineKeyboardMarkup:
    """
    Inline-кнопки «Выключить [название]» по одной на каждый элемент.

    callback_data: fin_<session_id> для hotkey или fin_plan_<plan_item_id> для запланированного.

    :param items: Список элементов (hotkey-сессии и/или запланированные события).
    :returns: InlineKeyboardMarkup; callback_data в пределах 64 байт.
    """
    buttons: list[list[InlineKeyboardButton]] = []
    for it in items:
        if it.session_id is not None:
            callback_data = f"{CALLBACK_PREFIX_FINISH}{it.session_id}"
        else:
            callback_data = f"{CALLBACK_PREFIX_FINISH_PLAN}{it.plan_item_id}"
        if not _callback_fits(callback_data):
            continue
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"Выключить {it.title}",
                    callback_data=callback_data,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
