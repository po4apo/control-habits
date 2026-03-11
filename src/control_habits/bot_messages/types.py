"""Типы и константы для bot_messages (формат callback_data для bot_handlers)."""

from dataclasses import dataclass
from datetime import datetime

# Префиксы callback_data (согласованы с bot_handlers; лимит Telegram 64 байта)
CALLBACK_PREFIX_HOTKEY = "hk_"  # hk_<activity_id>
CALLBACK_PREFIX_FINISH = "fin_"  # fin_<session_id>
CALLBACK_PREFIX_ACTIVE = "act_"  # кнопка «Что включено»
CALLBACK_PREFIX_ACTIVE_DETAIL = "actd_"  # деталь сессии: actd_<session_id>
CALLBACK_PREFIX_ACTIVE_DETAIL_PLAN = "actd_plan_"  # деталь запланированного события: actd_plan_<plan_item_id>
CALLBACK_PREFIX_FINISH_PLAN = "fin_plan_"  # выключить запланированное событие: fin_plan_<plan_item_id>
CALLBACK_PREFIX_HOTKEYS_MENU = "hkmenu_"  # открытие меню горячих клавиш

# Баг-репорт: подтверждение отправки / отмена
CALLBACK_PREFIX_BUG_CONFIRM = "bug_ok_"  # bug_ok_<draft_id>
CALLBACK_PREFIX_BUG_CANCEL = "bug_cn_"  # bug_cn_<draft_id>

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
    Представление активной сессии (hotkey) для сообщений и кнопок.

    Используется в build_active_sessions_message и build_finish_buttons.
    Caller (hotkey_sessions / bot_handlers) формирует список из БД с подгруженными названиями активностей.
    """

    session_id: int
    activity_name: str
    started_at: datetime


@dataclass(frozen=True)
class CurrentlyOnItem:
    """
    Элемент «что сейчас включено»: либо hotkey-сессия, либо запланированное событие (Начал, но ещё не Закончил).

    Для hotkey: session_id задан, plan_item_id None. Для запланированного: plan_item_id задан, session_id None.
    """

    session_id: int | None  # hotkey-сессия
    plan_item_id: int | None  # запланированное событие из расписания
    title: str
    started_at: datetime
