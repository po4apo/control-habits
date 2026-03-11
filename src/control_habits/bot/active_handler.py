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
    build_detail_buttons,
    build_session_detail_message,
)
from control_habits.bot_messages.types import (
    CALLBACK_PREFIX_ACTIVE_DETAIL,
    CALLBACK_PREFIX_ACTIVE_DETAIL_PLAN,
    CALLBACK_PREFIX_ACTIVE,
    CALLBACK_PREFIX_FINISH,
    CALLBACK_PREFIX_FINISH_PLAN,
    CALLBACK_PREFIX_PAUSE_PLAN,
    CALLBACK_PREFIX_RESUME_PLAN,
    ActiveSession as ActiveSessionDto,
    CurrentlyOnItem,
)
from control_habits.hotkey_sessions import (
    list_active_sessions,
    pause_session,
    resume_session,
    stop_session,
)
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.logs import LogsRepo
from control_habits.storage.repositories.schedule import ScheduleRepo
from control_habits.storage.repositories.sessions import TimeSegmentRepo
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


class PausePlanCallbackFilter(Filter):
    """Фильтр: callback_data — кнопка «Пауза» (префикс pp_)."""

    async def __call__(self, callback: CallbackQuery) -> bool:
        if not callback.data:
            return False
        return callback.data.startswith(CALLBACK_PREFIX_PAUSE_PLAN)


class ResumePlanCallbackFilter(Filter):
    """Фильтр: callback_data — кнопка «Продолжить» (префикс rp_)."""

    async def __call__(self, callback: CallbackQuery) -> bool:
        if not callback.data:
            return False
        return callback.data.startswith(CALLBACK_PREFIX_RESUME_PLAN)


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


def _parse_pause_resume_callback_data(data: str) -> int | None:
    """
    Разобрать callback_data: pp_<plan_item_id> или rp_<plan_item_id>.

    :param data: Строка callback_data.
    :returns: plan_item_id или None.
    """
    for prefix in (CALLBACK_PREFIX_PAUSE_PLAN, CALLBACK_PREFIX_RESUME_PLAN):
        if data.startswith(prefix):
            suffix = data[len(prefix) :].strip()
            if not suffix:
                return None
            try:
                return int(suffix)
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
    segments_repo: TimeSegmentRepo,
    activity_repo: ActivityRepo,
    logs_repo: LogsRepo,
    schedule_repo: ScheduleRepo,
) -> list[CurrentlyOnItem]:
    """Собрать список: открытые отрезки (hotkey + запланированные) + запланированные на паузе."""
    tz = ZoneInfo(user_timezone)
    now_local = datetime.now(timezone.utc).astimezone(tz)
    today = now_local.date()
    utc_start = datetime.combine(today, time(0, 0), tzinfo=tz).astimezone(timezone.utc)
    next_day = today + timedelta(days=1)
    utc_end = datetime.combine(next_day, time(0, 0), tzinfo=tz).astimezone(timezone.utc)

    items: list[CurrentlyOnItem] = []
    open_segments = segments_repo.list_open(user_id)
    for seg in open_segments:
        activity = activity_repo.get_by_id(seg.activity_id)
        name = activity.name if activity else "Активность"
        if seg.plan_item_id is not None:
            plan_item = schedule_repo.get_plan_item(seg.plan_item_id)
            title = (plan_item.title if plan_item else None) or name
        else:
            title = name
        items.append(
            CurrentlyOnItem(
                session_id=seg.id,
                plan_item_id=seg.plan_item_id,
                title=title,
                started_at=seg.started_at,
                is_paused=False,
            )
        )
    closed_today = segments_repo.list_segments_in_range(
        user_id, utc_start, utc_end
    )
    plan_item_ids_with_segments: set[int] = set()
    first_started: dict[int, datetime] = {}
    last_ended: dict[int, datetime] = {}
    for seg in closed_today:
        if seg.plan_item_id is not None:
            plan_item_ids_with_segments.add(seg.plan_item_id)
            if seg.plan_item_id not in first_started or seg.started_at < first_started[seg.plan_item_id]:
                first_started[seg.plan_item_id] = seg.started_at
            if seg.ended_at and (seg.plan_item_id not in last_ended or seg.ended_at > last_ended[seg.plan_item_id]):
                last_ended[seg.plan_item_id] = seg.ended_at
    for plan_item_id in plan_item_ids_with_segments:
        if segments_repo.get_open_by_plan_item(user_id, plan_item_id) is not None:
            continue
        if logs_repo.exists_by_idempotency_key(f"plan_end_{plan_item_id}_{today.isoformat()}"):
            continue
        plan_item = schedule_repo.get_plan_item(plan_item_id)
        title = (plan_item.title if plan_item else None) or "Событие"
        items.append(
            CurrentlyOnItem(
                session_id=None,
                plan_item_id=plan_item_id,
                title=title,
                started_at=first_started[plan_item_id],
                is_paused=True,
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
            TimeSegmentRepo,
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

            paused_at: datetime | None = None
            if kind == "session":
                segment = sessions_repo.get_by_id(item_id)
                if segment is None or segment.user_id != user.id:
                    await callback.answer("Не найдено.", show_alert=True)
                    return
                if segment.ended_at is not None:
                    await callback.answer("Сессия уже завершена.", show_alert=False)
                    return
                act = activity_repo.get_by_id(segment.activity_id)
                title = (act.name if act else None) or "Активность"
                item = CurrentlyOnItem(
                    session_id=segment.id,
                    plan_item_id=None,
                    title=title,
                    started_at=segment.started_at,
                    is_paused=False,
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
                open_seg = sessions_repo.get_open_by_plan_item(user.id, item_id)
                if open_seg is not None:
                    item = CurrentlyOnItem(
                        session_id=open_seg.id,
                        plan_item_id=item_id,
                        title=plan_item.title or "Событие",
                        started_at=open_seg.started_at,
                        is_paused=False,
                    )
                    paused_at = None
                else:
                    if logs_repo.exists_by_idempotency_key(f"plan_end_{item_id}_{today.isoformat()}"):
                        await callback.answer("Событие уже выключено.", show_alert=False)
                        return
                    closed = sessions_repo.list_segments_in_range(user.id, utc_start, utc_end)
                    first_started = None
                    paused_at = None
                    for seg in closed:
                        if seg.plan_item_id == item_id:
                            if first_started is None or seg.started_at < first_started:
                                first_started = seg.started_at
                            if seg.ended_at and (paused_at is None or seg.ended_at > paused_at):
                                paused_at = seg.ended_at
                    if first_started is None:
                        await callback.answer("Событие уже выключено.", show_alert=False)
                        return
                    item = CurrentlyOnItem(
                        session_id=None,
                        plan_item_id=item_id,
                        title=plan_item.title or "Событие",
                        started_at=first_started,
                        is_paused=True,
                    )

            text = build_session_detail_message(
                item.title,
                item.started_at,
                is_paused=item.is_paused,
                paused_at=paused_at if item.is_paused else None,
            )
            reply_markup = build_detail_buttons(item)
            await callback.answer()
            if callback.message:
                await callback.message.answer(text, reply_markup=reply_markup)
        finally:
            db_session.close()

    @router.callback_query(PausePlanCallbackFilter())
    async def on_pause_plan_callback(callback: CallbackQuery) -> None:
        """По нажатию «Пауза»: закрыть открытый отрезок."""
        plan_item_id = _parse_pause_resume_callback_data(callback.data or "")
        if plan_item_id is None:
            await callback.answer("Ошибка формата кнопки.", show_alert=True)
            return
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
            plan_item = schedule_repo.get_plan_item(plan_item_id)
            if plan_item is None:
                await callback.answer("Не найдено.", show_alert=True)
                return
            activity_id = plan_item.activity_id
            if activity_id is None:
                await callback.answer("Событие не привязано к активности.", show_alert=True)
                return
            now = datetime.now(timezone.utc)
            duration = pause_session(
                sessions_repo=sessions_repo,
                user_id=user.id,
                activity_id=activity_id,
                now=now,
                plan_item_id=plan_item_id,
            )
            if duration is None:
                await callback.answer("Уже на паузе или выключено.", show_alert=False)
                return
            db_session.commit()
            tz = ZoneInfo(user.timezone)
            today = datetime.now(timezone.utc).astimezone(tz).date()
            utc_start = datetime.combine(today, time(0, 0), tzinfo=tz).astimezone(timezone.utc)
            utc_end = datetime.combine(today + timedelta(days=1), time(0, 0), tzinfo=tz).astimezone(timezone.utc)
            closed = sessions_repo.list_segments_in_range(user.id, utc_start, utc_end)
            paused_at = None
            for seg in closed:
                if seg.plan_item_id == plan_item_id and seg.ended_at:
                    if paused_at is None or seg.ended_at > paused_at:
                        paused_at = seg.ended_at
            first_started = None
            for seg in closed:
                if seg.plan_item_id == plan_item_id:
                    if first_started is None or seg.started_at < first_started:
                        first_started = seg.started_at
            item = CurrentlyOnItem(
                session_id=None,
                plan_item_id=plan_item_id,
                title=plan_item.title or "Событие",
                started_at=first_started or now,
                is_paused=True,
            )
            text = build_session_detail_message(
                item.title,
                item.started_at,
                is_paused=True,
                paused_at=paused_at,
            )
            reply_markup = build_detail_buttons(item)
            await callback.answer("На паузе.")
            if callback.message:
                await callback.message.edit_text(text, reply_markup=reply_markup)
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()

    @router.callback_query(ResumePlanCallbackFilter())
    async def on_resume_plan_callback(callback: CallbackQuery) -> None:
        """По нажатию «Продолжить»: создать новый отрезок."""
        plan_item_id = _parse_pause_resume_callback_data(callback.data or "")
        if plan_item_id is None:
            await callback.answer("Ошибка формата кнопки.", show_alert=True)
            return
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
            plan_item = schedule_repo.get_plan_item(plan_item_id)
            if plan_item is None:
                await callback.answer("Не найдено.", show_alert=True)
                return
            activity_id = plan_item.activity_id
            if activity_id is None:
                await callback.answer("Событие не привязано к активности.", show_alert=True)
                return
            now = datetime.now(timezone.utc)
            resume_session(
                sessions_repo=sessions_repo,
                user_id=user.id,
                activity_id=activity_id,
                now=now,
                plan_item_id=plan_item_id,
            )
            db_session.commit()
            open_seg = sessions_repo.get_open_by_plan_item(user.id, plan_item_id)
            if open_seg is None:
                await callback.answer("Ошибка при возобновлении.", show_alert=True)
                return
            item = CurrentlyOnItem(
                session_id=open_seg.id,
                plan_item_id=plan_item_id,
                title=plan_item.title or "Событие",
                started_at=open_seg.started_at,
                is_paused=False,
            )
            text = build_session_detail_message(item.title, item.started_at)
            reply_markup = build_detail_buttons(item)
            await callback.answer("Продолжено.")
            if callback.message:
                await callback.message.edit_text(text, reply_markup=reply_markup)
        except Exception:
            db_session.rollback()
            raise
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
                open_seg = sessions_repo.get_open_by_plan_item(user.id, item_id)
                if open_seg is not None:
                    sessions_repo.close(open_seg.id, now)
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

            segment = sessions_repo.get_by_id(item_id)
            if segment is None or segment.user_id != user.id:
                await callback.answer("Не найдено.", show_alert=True)
                return

            if segment.ended_at is not None:
                await callback.answer(MSG_ALREADY_FINISHED, show_alert=False)
                await _edit_finish_message_to_done(callback, done_text=MSG_ALREADY_FINISHED)
                return

            now = datetime.now(timezone.utc)
            stop_session(
                sessions_repo=sessions_repo,
                user_id=user.id,
                activity_id=segment.activity_id,
                now=now,
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
