"""Обработка необработанных апдейтов: осмысленное логирование без «Update is not handled»."""

import logging
from collections.abc import Callable

from aiogram import Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.orm import Session

from control_habits.bot_messages import build_main_menu_reply_keyboard
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.hotkeys import HotkeysRepo
from control_habits.storage.repositories.users import UsersRepo

logger = logging.getLogger(__name__)

MSG_UNKNOWN_MESSAGE = (
    "Используйте команды /start и /active или кнопки в сообщениях выше."
)
MSG_KNOWN_USER = (
    "Дела по расписанию приходят в бот уведомлениями. "
    "Используйте «Что включено» и «Горячие клавиши» ниже."
)
MSG_UNKNOWN_BUTTON = "Неизвестная кнопка."


def setup_fallback_handler(
    router: Router,
    get_keyboard_deps: Callable[
        [], tuple[UsersRepo, HotkeysRepo, ActivityRepo, Session]
    ],
) -> None:
    """
    Регистрирует fallback-хендлеры для message и callback_query.

    Должны подключаться последними, чтобы не перехватывать /start, /active,
    кнопку «Что включено», callback пушей, hotkey и «Выключить».
    Логируем тип и данные апдейта и даём короткий ответ пользователю,
    чтобы диспетчер aiogram не логировал «Update id=... is not handled».
    Для привязанного пользователя прикладывается клавиатура hotkeys.

    :param router: Роутер aiogram.
    :param get_keyboard_deps: Функция, возвращающая (UsersRepo, HotkeysRepo, ActivityRepo, Session).
    """
    @router.message()
    async def on_unhandled_message(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else None
        text_preview = (message.text or message.caption or "")[:100]
        logger.info(
            "Необработанное сообщение: user_id=%s, text=%r",
            user_id,
            text_preview or "(без текста)",
        )
        users_repo, hotkeys_repo, activity_repo, session = get_keyboard_deps()
        try:
            user = (
                users_repo.get_by_telegram_id(user_id)
                if user_id is not None
                else None
            )
            if user is not None:
                keyboard = build_main_menu_reply_keyboard()
                await message.answer(MSG_KNOWN_USER, reply_markup=keyboard)
            else:
                await message.answer(MSG_UNKNOWN_MESSAGE)
        finally:
            session.close()

    @router.callback_query()
    async def on_unhandled_callback(callback: CallbackQuery) -> None:
        user_id = callback.from_user.id if callback.from_user else None
        logger.info(
            "Необработанный callback: user_id=%s, data=%r",
            user_id,
            callback.data,
        )
        await callback.answer(MSG_UNKNOWN_BUTTON, show_alert=False)
