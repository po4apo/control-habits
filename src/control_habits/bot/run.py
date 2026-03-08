"""Запуск бота (long polling). Регистрирует хендлер /start и опрашивает Telegram."""

import asyncio
import logging
import sys
import threading

from apscheduler.schedulers.blocking import BlockingScheduler
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from control_habits.auth_linking import AuthLinkingService
from control_habits.bot.active_handler import setup_active_handler
from control_habits.bot.fallback_handler import setup_fallback_handler
from control_habits.bot.hotkey_handler import setup_hotkey_handler
from control_habits.bot.push_callback_handler import setup_push_callback_handler
from control_habits.bot.start_handler import setup_start_handler
from control_habits.config import Settings
from control_habits.scheduler import PushSchedulerService
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.link_codes import LinkCodesRepo
from control_habits.storage.repositories.logs import LogsRepo
from control_habits.storage.repositories.notifications import NotificationsRepo
from control_habits.storage.repositories.sessions import SessionsRepo
from control_habits.storage.repositories.users import UsersRepo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def run_polling() -> None:
    """Создаёт бота, подключает хендлер /start и запускает long polling."""
    settings = Settings()
    if not settings.bot_token:
        logger.error("BOT_TOKEN не задан")
        sys.exit(1)

    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )
    session_factory = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    def get_auth_service() -> tuple[AuthLinkingService, Session]:
        session = session_factory()
        link_codes_repo = LinkCodesRepo(session)
        users_repo = UsersRepo(session)
        service = AuthLinkingService(
            link_codes_repo=link_codes_repo,
            users_repo=users_repo,
        )
        return service, session

    def get_push_callback_deps() -> tuple[
        UsersRepo, LogsRepo, NotificationsRepo, Session
    ]:
        session = session_factory()
        users_repo = UsersRepo(session)
        logs_repo = LogsRepo(session)
        notifications_repo = NotificationsRepo(session)
        return users_repo, logs_repo, notifications_repo, session

    def get_session_deps() -> tuple[
        UsersRepo, SessionsRepo, ActivityRepo, LogsRepo, Session
    ]:
        session = session_factory()
        users_repo = UsersRepo(session)
        sessions_repo = SessionsRepo(session)
        activity_repo = ActivityRepo(session)
        logs_repo = LogsRepo(session)
        return users_repo, sessions_repo, activity_repo, logs_repo, session

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    router = Router()
    setup_start_handler(
        router,
        get_auth_service=get_auth_service,
        web_app_url=settings.web_app_url,
    )
    setup_push_callback_handler(router, get_push_callback_deps)
    setup_hotkey_handler(router, get_session_deps)
    setup_active_handler(router, get_session_deps)
    setup_fallback_handler(router)  # последним: ловит необработанные message/callback
    dp.include_router(router)

    # Планировщик пушей в фоновом потоке (get_pending_locked, отправка, mark_sent)
    push_scheduler = PushSchedulerService(
        session_factory=session_factory,
        bot_token=settings.bot_token,
        interval_seconds=settings.scheduler_interval_seconds,
    )
    scheduler = BlockingScheduler()
    scheduler.add_job(
        push_scheduler.run_tick,
        "interval",
        seconds=settings.scheduler_interval_seconds,
        id="push_tick",
    )
    scheduler_thread = threading.Thread(target=scheduler.start, daemon=True)
    scheduler_thread.start()
    logger.info(
        "Планировщик пушей запущен (интервал %s с)",
        settings.scheduler_interval_seconds,
    )

    async def main() -> None:
        await dp.start_polling(bot)

    asyncio.run(main())


if __name__ == "__main__":
    run_polling()
