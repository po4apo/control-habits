"""Обработчик команды /start: привязка по коду и приветствие без кода."""

from collections.abc import Callable

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.orm import Session

from control_habits.auth_linking import AuthLinkingService, ConsumeLinkResult

# Тексты по docs/ui-telegram.md
MSG_WELCOME = (
    "Привет! Я бот для трекинга дел и привычек.\n\n"
    "Чтобы начать, зайди на сайт {url}, нажми «Войти через Telegram» и открой меня по ссылке с кодом — так мы привяжем твой аккаунт."
)
MSG_LINKED = (
    "Готово! Твой аккаунт привязан к сайту. Можешь вернуться в браузер и настроить расписание и кнопки."
)
MSG_EXPIRED = (
    "Код устарел. Запроси новый код на сайте и открой меня снова по новой ссылке."
)
MSG_ALREADY_USED = (
    "Этот код уже использован. Если нужно привязать другой аккаунт — запроси новый код на сайте."
)
MSG_NOT_FOUND = (
    "Код не найден. Запроси код на сайте и открой меня по ссылке с кодом."
)
DEFAULT_WEB_URL = "https://example.com"


def get_message_for_consume_result(result: ConsumeLinkResult) -> str:
    """
    Текст ответа пользователю по результату consume_link_code.

    :param result: Результат потребления кода.
    :returns: Текст сообщения для чата.
    """
    if result.success:
        return MSG_LINKED
    if result.reason == "expired":
        return MSG_EXPIRED
    if result.reason == "already_used":
        return MSG_ALREADY_USED
    return MSG_NOT_FOUND


def setup_start_handler(
    router: Router,
    get_auth_service: Callable[[], tuple[AuthLinkingService, Session]],
    web_app_url: str = "",
) -> None:
    """
    Регистрирует обработчик /start (с кодом — consume_link_code, без кода — приветствие).

    :param router: Роутер aiogram.
    :param get_auth_service: Функция, возвращающая (AuthLinkingService, session).
                             После использования сервиса вызывающий должен вызвать session.commit() и session.close().
    :param web_app_url: URL веб-приложения для текста приветствия (без кода).
    """
    url = (web_app_url or DEFAULT_WEB_URL).strip()

    @router.message(CommandStart())
    async def cmd_start(
        message: Message,
        command: CommandObject | None = None,
    ) -> None:
        if command is None or not command.args:
            text = MSG_WELCOME.format(url=url)
            await message.answer(text)
            return

        code = command.args.strip()
        if not code:
            text = MSG_WELCOME.format(url=url)
            await message.answer(text)
            return

        service, session = get_auth_service()
        try:
            telegram_user_id = message.from_user.id if message.from_user else 0
            result = service.consume_link_code(
                code=code, telegram_user_id=telegram_user_id
            )
            session.commit()
            text = get_message_for_consume_result(result)
            await message.answer(text)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
