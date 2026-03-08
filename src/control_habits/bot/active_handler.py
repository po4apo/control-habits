"""Команда /active (и кнопка «Что сейчас идёт») и callback «Закончить» по session_id."""

from collections.abc import Callable
from datetime import datetime, timezone

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, Filter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.orm import Session

from control_habits.bot_messages import (
    build_active_sessions_message,
    build_finish_buttons,
)
from control_habits.bot_messages.types import (
    CALLBACK_PREFIX_FINISH,
    ActiveSession as ActiveSessionDto,
)
from control_habits.hotkey_sessions import list_active_sessions
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.logs import LogsRepo
from control_habits.storage.repositories.sessions import SessionsRepo
from control_habits.storage.repositories.users import UsersRepo


# Текст кнопки «Что сейчас идёт» по docs/system-design.md
ACTIVE_BUTTON_TEXT = "Что сейчас идёт"

MSG_ALREADY_FINISHED = "Уже закончено."
MSG_FINISHED = "Закончено."


class FinishCallbackFilter(Filter):
    """Фильтр: callback_data — кнопка «Закончить» (префикс fin_)."""

    async def __call__(self, callback: CallbackQuery) -> bool:
        if not callback.data:
            return False
        return callback.data.startswith(CALLBACK_PREFIX_FINISH)


def _parse_finish_callback_data(data: str) -> int | None:
    """
    Разобрать callback_data: fin_<session_id>.

    :param data: Строка callback_data.
    :returns: session_id или None при неверном формате.
    """
    if not data.startswith(CALLBACK_PREFIX_FINISH):
        return None
    suffix = data[len(CALLBACK_PREFIX_FINISH) :].strip()
    if not suffix:
        return None
    try:
        return int(suffix)
    except ValueError:
        return None


def _sessions_to_dtos(sessions: list) -> list[ActiveSessionDto]:
    """Преобразовать список сессий из БД (с activity_name) в DTO для bot_messages."""
    return [
        ActiveSessionDto(
            session_id=s.id,
            activity_name=getattr(s, "activity_name", None) or "",
            started_at=s.started_at,
        )
        for s in sessions
    ]


def setup_active_handler(
    router: Router,
    get_deps: Callable[
        [],
        tuple[
            UsersRepo,
            SessionsRepo,
            ActivityRepo,
            LogsRepo,
            Session,
        ],
    ],
) -> None:
    """
    Регистрирует обработчик /active, текста «Что сейчас идёт» и callback «Закончить».

    /active и кнопка: list_active_sessions → build_active_sessions_message +
    build_finish_buttons → отправка сообщения.
    Callback «Закончить»: по session_id — stop_session, LogEntry session_end,
    идемпотентность по ключу fin_<session_id>.

    :param router: Роутер aiogram.
    :param get_deps: Функция, возвращающая (UsersRepo, SessionsRepo, ActivityRepo, LogsRepo, Session).
    """

    @router.message(Command("active"))
    async def cmd_active(message: Message) -> None:
        telegram_user_id = message.from_user.id if message.from_user else 0
        users_repo, sessions_repo, activity_repo, logs_repo, db_session = get_deps()
        try:
            user = users_repo.get_by_telegram_id(telegram_user_id)
            if user is None:
                await message.answer(
                    "Сначала привяжи аккаунт через /start."
                )
                return

            sessions = list_active_sessions(
                sessions_repo=sessions_repo,
                activity_repo=activity_repo,
                user_id=user.id,
            )
            dtos = _sessions_to_dtos(sessions)
            text = build_active_sessions_message(dtos)
            reply_markup = build_finish_buttons(dtos)
            await message.answer(text, reply_markup=reply_markup)
        finally:
            db_session.close()

    @router.message(lambda m: m.text and m.text.strip() == ACTIVE_BUTTON_TEXT)
    async def msg_active_button(message: Message) -> None:
        """Обработка нажатия кнопки «Что сейчас идёт» (то же, что /active)."""
        await cmd_active(message)

    @router.callback_query(FinishCallbackFilter())
    async def on_finish_callback(callback: CallbackQuery) -> None:
        session_id = _parse_finish_callback_data(callback.data or "")
        if session_id is None:
            await callback.answer("Ошибка формата кнопки.", show_alert=True)
            return

        telegram_user_id = callback.from_user.id if callback.from_user else 0
        idempotency_key = f"{CALLBACK_PREFIX_FINISH}{session_id}"

        users_repo, sessions_repo, activity_repo, logs_repo, db_session = get_deps()
        try:
            user = users_repo.get_by_telegram_id(telegram_user_id)
            if user is None:
                await callback.answer(
                    "Сначала привяжи аккаунт через /start.",
                    show_alert=True,
                )
                return

            already_logged = logs_repo.exists_by_idempotency_key(idempotency_key)
            if already_logged:
                await callback.answer(MSG_ALREADY_FINISHED, show_alert=False)
                await _edit_finish_message_to_done(callback, done_text=MSG_ALREADY_FINISHED)
                return

            session_row = sessions_repo.get_by_id(session_id)
            if session_row is None or session_row.user_id != user.id:
                await callback.answer("Сессия не найдена.", show_alert=True)
                return

            if session_row.ended_at is not None:
                await callback.answer(MSG_ALREADY_FINISHED, show_alert=False)
                await _edit_finish_message_to_done(callback, done_text=MSG_ALREADY_FINISHED)
                return

            now = datetime.now(timezone.utc)
            duration = stop_session(
                sessions_repo=sessions_repo,
                user_id=user.id,
                activity_id=session_row.activity_id,
                now=now,
            )
            if duration is not None:
                logs_repo.add(
                    user_id=user.id,
                    responded_at=now,
                    action="session_end",
                    activity_id=session_row.activity_id,
                    payload={
                        "idempotency_key": idempotency_key,
                        "session_id": session_id,
                        "duration_seconds": duration,
                    },
                )
            db_session.commit()

            await callback.answer(MSG_FINISHED, show_alert=False)
            await _edit_finish_message_to_done(callback, done_text=MSG_FINISHED)
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()


async def _edit_finish_message_to_done(
    callback: CallbackQuery,
    done_text: str,
) -> None:
    """Обновить сообщение: добавить подпись об окончании или убрать кнопки."""
    if not callback.message or not callback.message.text:
        return
    new_text = callback.message.text.rstrip()
    if not new_text.endswith(done_text):
        new_text = f"{new_text}\n{done_text}"
    try:
        await callback.message.edit_text(new_text, reply_markup=None)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
