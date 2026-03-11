"""Диалог отправки баг-репорта: кнопка в меню, ввод описания, подтверждение/отмена, отправка в GitHub."""

import logging
from collections.abc import Callable

from aiogram import Router
from aiogram.filters import Command, Filter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.orm import Session

from control_habits.bot_messages import (
    BUG_REPORT_BUTTON_LABEL,
    build_bug_confirm_keyboard,
    build_main_menu_reply_keyboard,
)
from control_habits.bot_messages.types import (
    CALLBACK_PREFIX_BUG_CANCEL,
    CALLBACK_PREFIX_BUG_CONFIRM,
)
from control_habits.bug_report import send_bug_report
from control_habits.bug_report.service import BugReportPayload, BugSendResult
from control_habits.storage.repositories.bug_report_drafts import (
    BugReportDraftRepo,
    STATE_WAITING_CONFIRM,
    STATE_WAITING_DESCRIPTION,
)
from control_habits.storage.repositories.users import UsersRepo

logger = logging.getLogger(__name__)

MSG_ASK_DESCRIPTION = (
    "Опиши, пожалуйста, проблему одним сообщением. "
    "Можно приложить скриншот или детали окружения."
)
MSG_NEED_DESCRIPTION = (
    "Нужно прислать текст описания бага или нажми /cancel для отмены."
)
MSG_PREVIEW_SEND_OR_CANCEL = (
    "Отправить этот баг-репорт в GitHub или отменить?"
)
MSG_USE_BUTTONS = "Нажми одну из кнопок выше: «Отправить» или «Отменить»."
MSG_SENT = "Спасибо! Баг отправлен: {url}"
MSG_SEND_FAILED = (
    "Не удалось отправить баг в GitHub (возможно, не настроен токен). "
    "Мы сохранили описание локально. Попробуй позже."
)
MSG_CANCELLED = "Отправка отменена."
MSG_NOT_LINKED = "Сначала привяжи аккаунт через /start."


class BugFlowMessageFilter(Filter):
    """Фильтр: у пользователя есть активный черновик баг-репорта (ожидание описания или подтверждения)."""

    def __init__(self, get_deps: Callable[[], tuple[UsersRepo, BugReportDraftRepo, Session]]) -> None:
        self._get_deps = get_deps

    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False
        _, drafts_repo, session = self._get_deps()
        try:
            draft = drafts_repo.get_active_by_telegram_id(message.from_user.id)
            return draft is not None
        finally:
            session.close()


def setup_bug_report_handler(
    router: Router,
    get_deps: Callable[
        [], tuple[UsersRepo, BugReportDraftRepo, Session]
    ],
    github_token: str = "",
    github_repo: str = "po4apo/control-habits",
) -> None:
    """
    Регистрирует хендлеры диалога баг-репорта: кнопка «Сообщить о баге», ввод описания, подтверждение.

    Подключать до fallback_handler. Требует привязанного пользователя.

    :param router: Роутер aiogram.
    :param get_deps: Функция, возвращающая (UsersRepo, BugReportDraftRepo, Session).
    :param github_token: GitHub PAT для создания Issue.
    :param github_repo: Репозиторий owner/repo.
    """
    keyboard = build_main_menu_reply_keyboard()

    @router.message(Command("cancel"), BugFlowMessageFilter(get_deps))
    async def on_cancel(message: Message) -> None:
        telegram_user_id = message.from_user.id if message.from_user else 0
        _, drafts_repo, session = get_deps()
        try:
            draft = drafts_repo.get_active_by_telegram_id(telegram_user_id)
            if draft is not None:
                drafts_repo.mark_cancelled(draft.id)
                session.commit()
            await message.answer(MSG_CANCELLED, reply_markup=keyboard)
        finally:
            session.close()

    @router.message(lambda m: m.text == BUG_REPORT_BUTTON_LABEL)
    async def on_bug_report_button(message: Message) -> None:
        telegram_user_id = message.from_user.id if message.from_user else 0
        users_repo, drafts_repo, session = get_deps()
        try:
            user = users_repo.get_by_telegram_id(telegram_user_id)
            if user is None:
                await message.answer(MSG_NOT_LINKED)
                return
            active = drafts_repo.get_active_by_telegram_id(telegram_user_id)
            if active is not None:
                await message.answer(
                    MSG_USE_BUTTONS if active.state == STATE_WAITING_CONFIRM else MSG_NEED_DESCRIPTION,
                    reply_markup=keyboard,
                )
                return
            draft = drafts_repo.create(user_id=user.id, telegram_user_id=telegram_user_id)
            session.commit()
            await message.answer(MSG_ASK_DESCRIPTION, reply_markup=keyboard)
        finally:
            session.close()

    @router.message(BugFlowMessageFilter(get_deps))
    async def on_message_during_bug_flow(message: Message) -> None:
        telegram_user_id = message.from_user.id if message.from_user else 0
        users_repo, drafts_repo, session = get_deps()
        try:
            draft = drafts_repo.get_active_by_telegram_id(telegram_user_id)
            if draft is None:
                return
            if draft.state == STATE_WAITING_DESCRIPTION:
                text = (message.text or "").strip()
                if not text:
                    await message.answer(MSG_NEED_DESCRIPTION, reply_markup=keyboard)
                    return
                drafts_repo.update_description(draft.id, text)
                session.commit()
                draft = drafts_repo.get_by_id(draft.id)
                if draft is None:
                    return
                preview = (draft.description[:200] + "…") if len(draft.description) > 200 else draft.description
                text = f"{preview}\n\n{MSG_PREVIEW_SEND_OR_CANCEL}"
                await message.answer(
                    text,
                    reply_markup=build_bug_confirm_keyboard(draft.id),
                )
                return
            if draft.state == STATE_WAITING_CONFIRM:
                await message.answer(MSG_USE_BUTTONS, reply_markup=keyboard)
        finally:
            session.close()

    async def _handle_bug_callback_confirm(callback: CallbackQuery, draft_id: int) -> None:
        users_repo, drafts_repo, session = get_deps()
        try:
            draft = drafts_repo.get_by_id(draft_id)
            if draft is None or draft.state != STATE_WAITING_CONFIRM:
                await callback.answer("Уже обработано или отменено.", show_alert=False)
                return
            username = callback.from_user.username if callback.from_user else None
            payload = BugReportPayload(
                description=draft.description,
                telegram_user_id=draft.telegram_user_id,
                username=username,
                user_id=draft.user_id,
            )
            result: BugSendResult = send_bug_report(
                payload,
                token=github_token,
                repo=github_repo,
            )
            if result.success and result.github_issue_url:
                drafts_repo.mark_sent(draft.id, result.github_issue_url)
                session.commit()
                await callback.answer("Отправлено.", show_alert=False)
                await callback.message.answer(
                    MSG_SENT.format(url=result.github_issue_url),
                    reply_markup=keyboard,
                )
            else:
                drafts_repo.mark_cancelled(draft.id)
                session.commit()
                await callback.answer("Ошибка отправки.", show_alert=True)
                await callback.message.answer(MSG_SEND_FAILED, reply_markup=keyboard)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def _handle_bug_callback_cancel(callback: CallbackQuery, draft_id: int) -> None:
        users_repo, drafts_repo, session = get_deps()
        try:
            draft = drafts_repo.get_by_id(draft_id)
            if draft is not None and draft.state == STATE_WAITING_CONFIRM:
                drafts_repo.mark_cancelled(draft.id)
                session.commit()
            await callback.answer("Отменено.", show_alert=False)
            await callback.message.answer(MSG_CANCELLED, reply_markup=keyboard)
        finally:
            session.close()

    @router.callback_query(lambda c: c.data and c.data.startswith(CALLBACK_PREFIX_BUG_CONFIRM))
    async def on_bug_confirm(callback: CallbackQuery) -> None:
        data = callback.data or ""
        suffix = data[len(CALLBACK_PREFIX_BUG_CONFIRM) :].strip()
        if not suffix or not suffix.isdigit():
            await callback.answer("Ошибка.", show_alert=True)
            return
        await _handle_bug_callback_confirm(callback, int(suffix))

    @router.callback_query(lambda c: c.data and c.data.startswith(CALLBACK_PREFIX_BUG_CANCEL))
    async def on_bug_cancel(callback: CallbackQuery) -> None:
        data = callback.data or ""
        suffix = data[len(CALLBACK_PREFIX_BUG_CANCEL) :].strip()
        if not suffix or not suffix.isdigit():
            await callback.answer("Ошибка.", show_alert=True)
            return
        await _handle_bug_callback_cancel(callback, int(suffix))
