"""Типы и константы для bot_messages (формат callback_data для bot_handlers)."""

from dataclasses import dataclass
from datetime import datetime

# Префиксы callback_data (согласованы с bot_handlers; лимит Telegram 64 байта)
CALLBACK_PREFIX_HOTKEY = "hk_"  # hk_<activity_id>
CALLBACK_PREFIX_FINISH = "fin_"  # fin_<session_id>

# Ответы на пуши: callback_data = префикс + str(notification_id).
# bot_handlers: парсить префикс → action, суффикс → notification_id; проверять идемпотентность по notification_id перед записью LogEntry.
CALLBACK_PREFIX_TASK_DONE = "td_"  # td_<notification_id>
CALLBACK_PREFIX_TASK_NOT_DONE = "tn_"  # tn_<notification_id>
CALLBACK_PREFIX_TASK_SKIP = "ts_"  # ts_<notification_id>
CALLBACK_PREFIX_EVENT_STARTED = "es_"  # es_<notification_id>
CALLBACK_PREFIX_EVENT_NOT_STARTED = "en_"  # en_<notification_id>
CALLBACK_PREFIX_EVENT_ENDED = "ee_"  # ee_<notification_id>
CALLBACK_PREFIX_EVENT_SKIPPED = "ek_"  # ek_<notification_id>


@dataclass(frozen=True)
class ActiveSession:
    """
    Представление активной сессии для сообщений и кнопок.

    Используется в build_active_sessions_message и build_finish_buttons.
    Caller (hotkey_sessions / bot_handlers) формирует список из БД с подгруженными названиями активностей.
    """

    session_id: int
    activity_name: str
    started_at: datetime
