"""Команда /active (и кнопка «Что включено») и callback «Выключить» по session_id или plan_item_id."""

from collections.abc import Callable
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, Filter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.orm import Session

from control_habits.bot_messages import (
    build_active_sessions_buttons,
    build_active_sessions_message,
    build_finish_buttons,
    build_session_detail_message,
)
from control_habits.bot_messages.types import (
    CALLBACK_PREFIX_ACTIVE_DETAIL,
    CALLBACK_PREFIX_ACTIVE_DETAIL_PLAN,
    CALLBACK_PREFIX_ACTIVE,
    CALLBACK_PREFIX_FINISH,
    CALLBACK_PREFIX_FINISH_PLAN,
    ActiveSession as ActiveSessionDto,
    CurrentlyOnItem,
)
from control_habits.hotkey_sessions import list_active_sessions, stop_session
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.logs import LogsRepo
from control_habits.storage.repositories.schedule import ScheduleRepo
from control_habits.storage.repositories.sessions import SessionsRepo
from control_habits.storage.repositories.users import UsersRepo


# Текст кнопки «Что включено» (должен совпадать с ACTIVE_BUTTON_LABEL в bot_messages.hotkeys)
ACTIVE_BUTTON_TEXT = "Что включено"

MSG_ALREADY_FINISHED = "Уже выключено."
MSG_FINISHED = "Выключено."


class ActiveCallbackFilter(Filter):
    """Фильтр: callback_data — кнопка «Что включено» (act_)."""

    async def __call__(self, callback: CallbackQuery) -> bool:
        if not callback.data:
            return False
        return callback.data == CALLBACK_PREFIX_ACTIVE


class ActiveDetailCallbackFilter(Filter):
    """Фильтр: callback_data — деталь сессии (префикс actd_)."""

    async def __call__(self, callback: CallbackQuery) -> bool:
        if not callback.data:
            return False
        return callback.data.startswith(CALLBACK_PREFIX_ACTIVE_DETAIL)


class FinishCallbackFilter(Filter):
    """Фильтр: callback_data — кнопка «Выключить» (префикс fin_)."""

    async def __call__(self, callback: CallbackQuery) -> bool:
        if not callback.data:
            return False
        return callback.data.startswith(CALLBACK_PREFIX_FINISH)


def _parse_active_detail_callback_data(data: str) -> tuple[str, int] | None:
    """
    Разобрать callback_data: actd_<session_id> или actd_plan_<plan_item_id>.

    :param data: Строка callback_data.
    :returns: ("session", session_id) или ("plan", plan_item_id), или None.
    """
    if data.startswith(CALLBACK_PREFIX_ACTIVE_DETAIL_PLAN):
        suffix = data[len(CALLBACK_PREFIX_ACTIVE_DETAIL_PLAN) :].strip()
        if not suffix:
            return None
        try:
            return ("plan", int(suffix))
        except ValueError:
            return None
    if data.startswith(CALLBACK_PREFIX_ACTIVE_DETAIL):
        suffix = data[len(CALLBACK_PREFIX_ACTIVE_DETAIL) :].strip()
        if not suffix:
            return None
        try:
            return ("session", int(suffix))
        except ValueError:
            return None
    return None


def _parse_finish_callback_data(data: str) -> tuple[str, int] | None:
    """
    Разобрать callback_data: fin_<session_id> или fin_plan_<plan_item_id>.

    :param data: Строка callback_data.
    :returns: ("session", session_id) или ("plan", plan_item_id), или None.
    """
    if data.startswith(CALLBACK_PREFIX_FINISH_PLAN):
        suffix = data[len(CALLBACK_PREFIX_FINISH_PLAN) :].strip()
        if not suffix:
            return None
        try:
            return ("plan", int(suffix))
        except ValueError:
            return None
    if not data.startswith(CALLBACK_PREFIX_FINISH):
        return None
    suffix = data[len(CALLBACK_PREFIX_FINISH) :].strip()
    if not suffix:
        return None
    try:
        return ("session", int(suffix))
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


def _build_currently_on_list(
    user_id: int,
    user_timezone: str,
    users_repo: UsersRepo,
    sessions_repo: SessionsRepo,
    activity_repo: ActivityRepo,
    logs_repo: LogsRepo,
    schedule_repo: ScheduleRepo,
) -> list[CurrentlyOnItem]:
    """Собрать объединённый список: hotkey-сессии + запланированные события «Начал», но ещё не «Закончил»."""
    tz = ZoneInfo(user_timezone)
    now_local = datetime.now(timezone.utc).astimezone(tz)
    today = now_local.date()
    utc_start = datetime.combine(today, time(0, 0), tzinfo=tz).astimezone(timezone.utc)
    next_day = today + timedelta(days=1)
    utc_end = datetime.combine(next_day, time(0, 0), tzinfo=tz).astimezone(timezone.utc)

    items: list[CurrentlyOnItem] = []
    sessions = list_active_sessions(
        sessions_repo=sessions_repo,
        activity_repo=activity_repo,
        user_id=user_id,
    )
    for s in sessions:
        name = getattr(s, "activity_name", None) or "Активность"
        items.append(
            CurrentlyOnItem(
                session_id=s.id,
                plan_item_id=None,
                title=name,
                started_at=s.started_at,
            )
        )
    planned_in_progress = logs_repo.list_planned_events_in_progress(
        user_id, utc_start, utc_end
    )
    for plan_item_id, started_at in planned_in_progress:
        plan_item = schedule_repo.get_plan_item(plan_item_id)
        title = (plan_item.title if plan_item else None) or "Событие"
        items.append(
            CurrentlyOnItem(
                session_id=None,
                plan_item_id=plan_item_id,
                title=title,
                started_at=started_at,
            )
        )
    items.sort(key=lambda x: x.started_at)
    return items


def setup_active_handler(
    router: Router,
    get_deps: Callable[
        [],
        tuple[
            UsersRepo,
            SessionsRepo,
            ActivityRepo,
            LogsRepo,
            ScheduleRepo,
            Session,
        ],
    ],
) -> None:
    """
    Регистрирует обработчик /active, текста «Что включено» и callback «Выключить».

    «Что включено»: hotkey-сессии + запланированные события (Начал, но ещё не Закончил).
    Callback «Выключить»: fin_<session_id> (hotkey) или fin_plan_<plan_item_id> (запланированное).

    :param router: Роутер aiogram.
    :param get_deps: Функция, возвращающая (UsersRepo, SessionsRepo, ActivityRepo, LogsRepo, ScheduleRepo, Session).
    """

    @router.message(Command("active"))
    async def cmd_active(message: Message) -> None:
        telegram_user_id = message.from_user.id if message.from_user else 0
        users_repo, sessions_repo, activity_repo, logs_repo, schedule_repo, db_session = get_deps()
        try:
            user = users_repo.get_by_telegram_id(telegram_user_id)
            if user is None:
                await message.answer(
                    "Сначала привяжи аккаунт через /start."
                )
                return
            items = _build_currently_on_list(
                user.id,
                user.timezone,
                users_repo,
                sessions_repo,
                activity_repo,
                logs_repo,
                schedule_repo,
            )
            text = build_active_sessions_message(items)
            reply_markup = build_active_sessions_buttons(items) if items else None
            await message.answer(text, reply_markup=reply_markup)
        finally:
            db_session.close()

    @router.message(lambda m: m.text and m.text.strip() == ACTIVE_BUTTON_TEXT)
    async def msg_active_button(message: Message) -> None:
        """Обработка нажатия кнопки «Что включено» (то же, что /active)."""
        await cmd_active(message)

    @router.callback_query(ActiveCallbackFilter())
    async def on_active_callback(callback: CallbackQuery) -> None:
        """Обработка inline-кнопки «Что включено» — тот же ответ, что /active."""
        telegram_user_id = callback.from_user.id if callback.from_user else 0
        users_repo, sessions_repo, activity_repo, logs_repo, schedule_repo, db_session = get_deps()
        try:
            user = users_repo.get_by_telegram_id(telegram_user_id)
            if user is None:
                await callback.answer(
                    "Сначала привяжи аккаунт через /start.",
                    show_alert=True,
                )
                return
            items = _build_currently_on_list(
                user.id,
                user.timezone,
                users_repo,
                sessions_repo,
                activity_repo,
                logs_repo,
                schedule_repo,
            )
            text = build_active_sessions_message(items)
            reply_markup = build_active_sessions_buttons(items) if items else None
            await callback.answer()
            if callback.message:
                await callback.message.answer(text, reply_markup=reply_markup)
        finally:
            db_session.close()

    @router.callback_query(ActiveDetailCallbackFilter())
    async def on_active_detail_callback(callback: CallbackQuery) -> None:
        """По нажатию на элемент в списке: «Событие X идёт с HH:MM» + кнопка «Выключить X»."""
        parsed = _parse_active_detail_callback_data(callback.data or "")
        if parsed is None:
            await callback.answer("Ошибка формата кнопки.", show_alert=True)
            return

        kind, item_id = parsed
        telegram_user_id = callback.from_user.id if callback.from_user else 0
        users_repo, sessions_repo, activity_repo, logs_repo, schedule_repo, db_session = get_deps()
        try:
            user = users_repo.get_by_telegram_id(telegram_user_id)
            if user is None:
                await callback.answer(
                    "Сначала привяжи аккаунт через /start.",
                    show_alert=True,
                )
                return

            if kind == "session":
                session_row = sessions_repo.get_by_id(item_id)
                if session_row is None or session_row.user_id != user.id:
                    await callback.answer("Не найдено.", show_alert=True)
                    return
                if session_row.ended_at is not None:
                    await callback.answer("Сессия уже завершена.", show_alert=False)
                    return
                act = activity_repo.get_by_id(session_row.activity_id)
                title = (act.name if act else None) or "Активность"
                item = CurrentlyOnItem(
                    session_id=session_row.id,
                    plan_item_id=None,
                    title=title,
                    started_at=session_row.started_at,
                )
            else:
                plan_item = schedule_repo.get_plan_item(item_id)
                if plan_item is None:
                    await callback.answer("Не найдено.", show_alert=True)
                    return
                tz = ZoneInfo(user.timezone)
                now_local = datetime.now(timezone.utc).astimezone(tz)
                today = now_local.date()
                utc_start = datetime.combine(today, time(0, 0), tzinfo=tz).astimezone(timezone.utc)
                utc_end = datetime.combine(today + timedelta(days=1), time(0, 0), tzinfo=tz).astimezone(timezone.utc)
                planned = logs_repo.list_planned_events_in_progress(user.id, utc_start, utc_end)
                started_at = None
                for pid, st in planned:
                    if pid == item_id:
                        started_at = st
                        break
                if started_at is None:
                    await callback.answer("Событие уже выключено.", show_alert=False)
                    return
                title = plan_item.title or "Событие"
                item = CurrentlyOnItem(
                    session_id=None,
                    plan_item_id=item_id,
                    title=title,
                    started_at=started_at,
                )

            text = build_session_detail_message(item.title, item.started_at)
            reply_markup = build_finish_buttons([item])
            await callback.answer()
            if callback.message:
                await callback.message.answer(text, reply_markup=reply_markup)
        finally:
            db_session.close()

    @router.callback_query(FinishCallbackFilter())
    async def on_finish_callback(callback: CallbackQuery) -> None:
        parsed = _parse_finish_callback_data(callback.data or "")
        if parsed is None:
            await callback.answer("Ошибка формата кнопки.", show_alert=True)
            return

        kind, item_id = parsed
        telegram_user_id = callback.from_user.id if callback.from_user else 0
        users_repo, sessions_repo, activity_repo, logs_repo, schedule_repo, db_session = get_deps()
        try:
            user = users_repo.get_by_telegram_id(telegram_user_id)
            if user is None:
                await callback.answer(
                    "Сначала привяжи аккаунт через /start.",
                    show_alert=True,
                )
                return

            if kind == "plan":
                tz = ZoneInfo(user.timezone)
                now_local = datetime.now(timezone.utc).astimezone(tz)
                today = now_local.date()
                idempotency_key = f"plan_end_{item_id}_{today.isoformat()}"
                if logs_repo.exists_by_idempotency_key(idempotency_key):
                    await callback.answer(MSG_ALREADY_FINISHED, show_alert=False)
                    await _edit_finish_message_to_done(callback, done_text=MSG_ALREADY_FINISHED)
                    return
                now = datetime.now(timezone.utc)
                logs_repo.add(
                    user_id=user.id,
                    responded_at=now,
                    action="event_ended",
                    plan_item_id=item_id,
                    payload={"idempotency_key": idempotency_key},
                )
                db_session.commit()
                await callback.answer(MSG_FINISHED, show_alert=False)
                await _edit_finish_message_to_done(callback, done_text=MSG_FINISHED)
                return

            idempotency_key = f"{CALLBACK_PREFIX_FINISH}{item_id}"
            already_logged = logs_repo.exists_by_idempotency_key(idempotency_key)
            if already_logged:
                await callback.answer(MSG_ALREADY_FINISHED, show_alert=False)
                await _edit_finish_message_to_done(callback, done_text=MSG_ALREADY_FINISHED)
                return

            session_row = sessions_repo.get_by_id(item_id)
            if session_row is None or session_row.user_id != user.id:
                await callback.answer("Не найдено.", show_alert=True)
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
                        "session_id": item_id,
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
    """Обновить сообщение: добавить подпись о выключении или убрать кнопки."""
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
