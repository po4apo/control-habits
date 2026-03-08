"""Обработка необработанных апдейтов: осмысленное логирование без «Update is not handled»."""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery, Message

logger = logging.getLogger(__name__)

MSG_UNKNOWN_MESSAGE = (
    "Используйте команды /start и /active или кнопки в сообщениях выше."
)
MSG_UNKNOWN_BUTTON = "Неизвестная кнопка."


def setup_fallback_handler(router: Router) -> None:
    """
    Регистрирует fallback-хендлеры для message и callback_query.

    Должны подключаться последними, чтобы не перехватывать /start, /active,
    кнопку «Что сейчас идёт», callback пушей, hotkey и «Закончить».
    Логируем тип и данные апдейта и даём короткий ответ пользователю,
    чтобы диспетчер aiogram не логировал «Update id=... is not handled».

    :param router: Роутер aiogram.
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
        await message.answer(MSG_UNKNOWN_MESSAGE)

    @router.callback_query()
    async def on_unhandled_callback(callback: CallbackQuery) -> None:
        user_id = callback.from_user.id if callback.from_user else None
        logger.info(
            "Необработанный callback: user_id=%s, data=%r",
            user_id,
            callback.data,
        )
        await callback.answer(MSG_UNKNOWN_BUTTON, show_alert=False)
