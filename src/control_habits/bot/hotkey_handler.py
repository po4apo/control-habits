"""Обработка нажатий hotkey-кнопок и меню «Горячие клавиши»: start_session/stop_session, LogEntry, ответ пользователю."""

from collections.abc import Callable
from datetime import datetime, timezone

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.orm import Session

from control_habits.bot_messages import build_hotkeys_keyboard, HOTKEYS_MENU_LABEL
from control_habits.bot_messages.types import (
    CALLBACK_PREFIX_HOTKEY,
    CALLBACK_PREFIX_HOTKEYS_MENU,
)
from control_habits.hotkey_sessions import start_session, stop_session
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.hotkeys import HotkeysRepo
from control_habits.storage.repositories.sessions import TimeSegmentRepo
from control_habits.storage.repositories.users import UsersRepo

MSG_HOTKEYS_CHOOSE = "Выберите событие:"


class HotkeysMenuCallbackFilter(Filter):
    """Фильтр: callback_data — кнопка «Горячие клавиши» (hkmenu_)."""

    async def __call__(self, callback: CallbackQuery) -> bool:
        if not callback.data:
            return False
        return callback.data == CALLBACK_PREFIX_HOTKEYS_MENU


class HotkeyCallbackFilter(Filter):
    """Фильтр: callback_data — нажатие hotkey (префикс hk_)."""

    async def __call__(self, callback: CallbackQuery) -> bool:
        if not callback.data:
            return False
        return callback.data.startswith(CALLBACK_PREFIX_HOTKEY)


def _parse_hotkey_callback_data(data: str) -> int | None:
    """
    Разобрать callback_data hotkey: hk_<activity_id>.

    :param data: Строка callback_data.
    :returns: activity_id или None при неверном формате.
    """
    if not data.startswith(CALLBACK_PREFIX_HOTKEY):
        return None
    suffix = data[len(CALLBACK_PREFIX_HOTKEY) :].strip()
    if not suffix:
        return None
    try:
        return int(suffix)
    except ValueError:
        return None


def _format_duration_minutes(seconds: float) -> str:
    """Форматирование длительности в минутах для ответа пользователю."""
    minutes = int(round(seconds / 60))
    if minutes < 1:
        return "меньше минуты"
    if minutes == 1:
        return "1 мин"
    return f"{minutes} мин"


def setup_hotkey_handler(
    router: Router,
    get_deps: Callable[
        [],
        tuple[UsersRepo, TimeSegmentRepo, ActivityRepo, Session],
    ],
    get_keyboard_deps: Callable[
        [],
        tuple[UsersRepo, HotkeysRepo, ActivityRepo, Session],
    ]
    | None = None,
) -> None:
    """
    Регистрирует обработчик callback_query для hotkey-кнопок и меню «Горячие клавиши».

    Логика hotkey: если активной сессии по активности нет — start_session, LogEntry session_start;
    иначе — stop_session, LogEntry session_end. Ответ пользователю с названием активности.
    Логика hkmenu_: отправить сообщение с клавиатурой только горячих кнопок (без «Что включено»).

    :param router: Роутер aiogram.
    :param get_deps: Функция, возвращающая (UsersRepo, SessionsRepo, ActivityRepo, LogsRepo, Session).
    :param get_keyboard_deps: Функция для сборки клавиатуры горячих клавиш (для hkmenu_); при None меню не регистрируется.
    """

    if get_keyboard_deps is not None:

        def _get_active_ids(user_id: int, db_session: Session) -> set[int]:
            """Получить множество activity_id с активными сессиями."""
            segments_repo = TimeSegmentRepo(db_session)
            active = segments_repo.list_active(user_id)
            return {s.activity_id for s in active}

        @router.message(lambda m: m.text and m.text.strip() == HOTKEYS_MENU_LABEL)
        async def on_hotkeys_menu_message(message: Message) -> None:
            """По нажатию Reply-кнопки «Горячие клавиши»: сообщение «Выберите событие» и inline-клавиатура hotkeys."""
            telegram_user_id = message.from_user.id if message.from_user else 0
            users_repo, hotkeys_repo, activity_repo, session = get_keyboard_deps()
            try:
                user = users_repo.get_by_telegram_id(telegram_user_id)
                if user is None:
                    await message.answer(
                        "Сначала привяжи аккаунт через /start.",
                    )
                    return
                active_ids = _get_active_ids(user.id, session)
                keyboard = build_hotkeys_keyboard(
                    user.id,
                    hotkeys_repo,
                    activity_repo,
                    include_active_button=False,
                    active_activity_ids=active_ids,
                )
                await message.answer(
                    MSG_HOTKEYS_CHOOSE,
                    reply_markup=keyboard,
                )
            finally:
                session.close()

        @router.callback_query(HotkeysMenuCallbackFilter())
        async def on_hotkeys_menu_callback(callback: CallbackQuery) -> None:
            """По нажатию «Горячие клавиши»: сообщение «Выберите событие» и клавиатура только hotkeys."""
            telegram_user_id = callback.from_user.id if callback.from_user else 0
            users_repo, hotkeys_repo, activity_repo, session = get_keyboard_deps()
            try:
                user = users_repo.get_by_telegram_id(telegram_user_id)
                if user is None:
                    await callback.answer(
                        "Сначала привяжи аккаунт через /start.",
                        show_alert=True,
                    )
                    return
                active_ids = _get_active_ids(user.id, session)
                keyboard = build_hotkeys_keyboard(
                    user.id,
                    hotkeys_repo,
                    activity_repo,
                    include_active_button=False,
                    active_activity_ids=active_ids,
                )
                await callback.answer()
                if callback.message:
                    await callback.message.answer(
                        MSG_HOTKEYS_CHOOSE,
                        reply_markup=keyboard,
                    )
            finally:
                session.close()

    @router.callback_query(HotkeyCallbackFilter())
    async def on_hotkey_callback(callback: CallbackQuery) -> None:
        activity_id = _parse_hotkey_callback_data(callback.data or "")
        if activity_id is None:
            await callback.answer("Ошибка формата кнопки.", show_alert=True)
            return

        telegram_user_id = callback.from_user.id if callback.from_user else 0
        users_repo, segments_repo, activity_repo, session = get_deps()
        try:
            user = users_repo.get_by_telegram_id(telegram_user_id)
            if user is None:
                await callback.answer(
                    "Сначала привяжи аккаунт через /start.",
                    show_alert=True,
                )
                return

            activity = activity_repo.get_by_id(activity_id)
            if activity is None or activity.user_id != user.id:
                await callback.answer("Событие не найдено.", show_alert=True)
                return

            now = datetime.now(timezone.utc)
            activity_name = activity.name or "Активность"

            existing = segments_repo.get_active(user.id, activity_id)
            if existing is None:
                start_session(
                    sessions_repo=segments_repo,
                    user_id=user.id,
                    activity_id=activity_id,
                    now=now,
                )
                session.commit()
                text = f"▶ {activity_name} включено."
            else:
                duration = stop_session(
                    sessions_repo=segments_repo,
                    user_id=user.id,
                    activity_id=activity_id,
                    now=now,
                )
                session.commit()
                if duration is not None:
                    text = f"⏹ {activity_name} выключено (шло {_format_duration_minutes(duration)})."
                else:
                    text = f"{activity_name} уже было выключено."

            await callback.answer(text, show_alert=True)
            await _update_hotkeys_keyboard(callback, user.id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def _update_hotkeys_keyboard(
        callback: CallbackQuery,
        user_id: int,
    ) -> None:
        """Обновить inline-клавиатуру: пометить активные сессии индикатором."""
        if get_keyboard_deps is None or not callback.message:
            return
        kb_users_repo, hotkeys_repo, kb_activity_repo, kb_session = get_keyboard_deps()
        try:
            kb_segments_repo = TimeSegmentRepo(kb_session)
            active_sessions = kb_segments_repo.list_active(user_id)
            active_ids = {s.activity_id for s in active_sessions}
            keyboard = build_hotkeys_keyboard(
                user_id,
                hotkeys_repo,
                kb_activity_repo,
                include_active_button=False,
                active_activity_ids=active_ids,
            )
            try:
                await callback.message.edit_reply_markup(reply_markup=keyboard)
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e):
                    raise
        finally:
            kb_session.close()
