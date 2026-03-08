"""Обработка нажатий hotkey-кнопок: start_session/stop_session, LogEntry, ответ пользователю."""

from collections.abc import Callable
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import CallbackQuery
from sqlalchemy.orm import Session

from control_habits.bot_messages.types import CALLBACK_PREFIX_HOTKEY
from control_habits.hotkey_sessions import start_session, stop_session
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.logs import LogsRepo
from control_habits.storage.repositories.sessions import SessionsRepo
from control_habits.storage.repositories.users import UsersRepo


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
        tuple[UsersRepo, SessionsRepo, ActivityRepo, LogsRepo, Session],
    ],
) -> None:
    """
    Регистрирует обработчик callback_query для hotkey-кнопок.

    Логика: если активной сессии по активности нет — start_session, LogEntry session_start;
    иначе — stop_session, LogEntry session_end. Ответ пользователю с названием активности.
    Идемпотентность: start_session возвращает существующий id при повторном старте;
    stop_session возвращает None при повторном стопе — запись LogEntry только при реальном действии.

    :param router: Роутер aiogram.
    :param get_deps: Функция, возвращающая (UsersRepo, SessionsRepo, ActivityRepo, LogsRepo, Session).
    """

    @router.callback_query(HotkeyCallbackFilter())
    async def on_hotkey_callback(callback: CallbackQuery) -> None:
        activity_id = _parse_hotkey_callback_data(callback.data or "")
        if activity_id is None:
            await callback.answer("Ошибка формата кнопки.", show_alert=True)
            return

        telegram_user_id = callback.from_user.id if callback.from_user else 0
        users_repo, sessions_repo, activity_repo, logs_repo, session = get_deps()
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
                await callback.answer("Активность не найдена.", show_alert=True)
                return

            now = datetime.now(timezone.utc)
            activity_name = activity.name or "Активность"

            existing = sessions_repo.get_active(user.id, activity_id)
            if existing is None:
                start_session(
                    sessions_repo=sessions_repo,
                    user_id=user.id,
                    activity_id=activity_id,
                    now=now,
                )
                logs_repo.add(
                    user_id=user.id,
                    responded_at=now,
                    action="session_start",
                    activity_id=activity_id,
                )
                session.commit()
                await callback.answer(f"Сессия «{activity_name}» начата.", show_alert=False)
            else:
                duration = stop_session(
                    sessions_repo=sessions_repo,
                    user_id=user.id,
                    activity_id=activity_id,
                    now=now,
                )
                if duration is not None:
                    logs_repo.add(
                        user_id=user.id,
                        responded_at=now,
                        action="session_end",
                        activity_id=activity_id,
                        payload={"duration_seconds": duration},
                    )
                session.commit()
                if duration is not None:
                    text = f"Сессия «{activity_name}» закончена ({_format_duration_minutes(duration)})."
                else:
                    text = f"Сессия «{activity_name}» уже была закончена."
                await callback.answer(text, show_alert=False)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
