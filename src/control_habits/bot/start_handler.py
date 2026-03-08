"""Обработчик команды /start: привязка по коду и приветствие без кода."""

from collections.abc import Callable

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.orm import Session

from control_habits.auth_linking import AuthLinkingService, ConsumeLinkResult
from control_habits.bot_messages import build_main_menu_reply_keyboard
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.hotkeys import HotkeysRepo
from control_habits.storage.repositories.users import UsersRepo

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

MSG_ALREADY_LINKED = (
    "Вы уже привязаны. Используйте «Что включено» и «Горячие клавиши»."
)
MSG_MAIN_MENU = (
    "Используйте «Что включено» или «Горячие клавиши»."
)
MSG_NO_HOTKEYS_YET = (
    "Добавьте кнопки событий на сайте в разделе «Кнопки». "
    "Пока используйте «Что включено» и «Горячие клавиши»."
)


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
    get_keyboard_deps: Callable[
        [], tuple[UsersRepo, HotkeysRepo, ActivityRepo, Session]
    ],
    web_app_url: str = "",
) -> None:
    """
    Регистрирует обработчик /start (с кодом — consume_link_code, без кода — приветствие или клавиатура).

    :param router: Роутер aiogram.
    :param get_auth_service: Функция, возвращающая (AuthLinkingService, session).
                             После использования сервиса вызывающий должен вызвать session.commit() и session.close().
    :param get_keyboard_deps: Функция, возвращающая (UsersRepo, HotkeysRepo, ActivityRepo, Session) для сборки клавиатуры.
    :param web_app_url: URL веб-приложения для текста приветствия (без кода).
    """
    url = (web_app_url or DEFAULT_WEB_URL).strip()

    async def _send_main_menu(
        message: Message,
        user_id: int,
        hotkeys_repo: HotkeysRepo,
        first_message: bool = False,
    ) -> None:
        """Отправить главное меню: Reply-клавиатура с «Что включено» и «Горячие клавиши»."""
        keyboard = build_main_menu_reply_keyboard()
        hotkeys = hotkeys_repo.list_by_user(user_id)
        if hotkeys:
            text = MSG_MAIN_MENU if first_message else MSG_ALREADY_LINKED
        else:
            text = MSG_NO_HOTKEYS_YET
        await message.answer(text, reply_markup=keyboard)

    @router.message(CommandStart())
    async def cmd_start(
        message: Message,
        command: CommandObject | None = None,
    ) -> None:
        telegram_user_id = message.from_user.id if message.from_user else 0

        if command is None or not command.args:
            # /start без кода: если уже привязан — показать клавиатуру
            users_repo, hotkeys_repo, activity_repo, session = get_keyboard_deps()
            try:
                user = users_repo.get_by_telegram_id(telegram_user_id)
                if user is not None:
                    await _send_main_menu(message, user.id, hotkeys_repo)
                    return
            finally:
                session.close()
            text = MSG_WELCOME.format(url=url)
            await message.answer(text)
            return

        code = command.args.strip()
        if not code:
            users_repo, hotkeys_repo, activity_repo, session = get_keyboard_deps()
            try:
                user = users_repo.get_by_telegram_id(telegram_user_id)
                if user is not None:
                    await _send_main_menu(message, user.id, hotkeys_repo)
                    return
            finally:
                session.close()
            text = MSG_WELCOME.format(url=url)
            await message.answer(text)
            return

        service, session = get_auth_service()
        try:
            result = service.consume_link_code(
                code=code, telegram_user_id=telegram_user_id
            )
            session.commit()
            text = get_message_for_consume_result(result)
            await message.answer(text)
            if result.success and result.user_id is not None:
                session.close()
                users_repo, hotkeys_repo, activity_repo, kb_session = get_keyboard_deps()
                try:
                    await _send_main_menu(
                        message,
                        result.user_id,
                        hotkeys_repo,
                        first_message=True,
                    )
                finally:
                    kb_session.close()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
