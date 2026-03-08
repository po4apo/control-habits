"""Зависимости FastAPI: сессия БД, сервис привязки, текущий пользователь."""

from collections.abc import Generator
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from control_habits.auth_linking import AuthLinkingService
from control_habits.config import Settings
from control_habits.storage.repositories.activity import ActivityRepo
from control_habits.storage.repositories.link_codes import LinkCodesRepo
from control_habits.storage.repositories.logs import LogsRepo
from control_habits.storage.repositories.hotkeys import HotkeysRepo
from control_habits.storage.repositories.schedule import ScheduleRepo
from control_habits.storage.repositories.sessions import SessionsRepo
from control_habits.storage.repositories.users import UsersRepo

# Заголовок с идентификатором веб-сессии (после привязки — запросы с ним считаются авторизованными).
WEB_SESSION_HEADER = "X-Web-Session-Id"


def get_settings() -> Settings:
    """Настройки приложения."""
    return Settings()


def get_db(request: Request) -> Generator[Session, None, None]:
    """
    Генератор сессии БД для FastAPI Depends.
    Ожидает, что session_factory установлен в app.state при старте приложения.

    :param request: Запрос FastAPI (для доступа к app.state).
    :yields: Сессия SQLAlchemy.
    """
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_auth_linking_service(
    session: Session = Depends(get_db),
) -> AuthLinkingService:
    """
    Сервис привязки для текущей сессии.

    :param session: Сессия БД (из get_db).
    :returns: Экземпляр AuthLinkingService.
    """
    link_codes_repo = LinkCodesRepo(session)
    users_repo = UsersRepo(session)
    return AuthLinkingService(
        link_codes_repo=link_codes_repo,
        users_repo=users_repo,
    )


def get_web_session_id(
    x_web_session_id: str | None = Header(None, alias=WEB_SESSION_HEADER),
) -> str | None:
    """
    Извлечь идентификатор веб-сессии из заголовка запроса.

    :param x_web_session_id: Значение заголовка X-Web-Session-Id.
    :returns: Идентификатор сессии или None.
    """
    return x_web_session_id


def get_current_user_id(
    web_session_id: str | None = Depends(get_web_session_id),
    service: AuthLinkingService = Depends(get_auth_linking_service),
) -> int:
    """
    Зависимость авторизации: вернуть user_id по привязанной веб-сессии.

    Требует заголовок X-Web-Session-Id с идентификатором сессии, которая уже
    прошла привязку через бота (consume_link_code). Иначе 401.

    :param web_session_id: Идентификатор веб-сессии из заголовка.
    :param service: Сервис привязки.
    :returns: Идентификатор пользователя.
    :raises HTTPException: 401 если сессия не передана или не привязана.
    """
    if not web_session_id:
        raise HTTPException(
            status_code=401,
            detail="Требуется заголовок X-Web-Session-Id с идентификатором привязанной сессии",
        )
    user_id = service.get_user_id_by_web_session(web_session_id)
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Сессия не привязана или не найдена",
        )
    return user_id


def get_schedule_repo(session: Session = Depends(get_db)) -> ScheduleRepo:
    """Репозиторий расписаний."""
    return ScheduleRepo(session)


def get_activity_repo(session: Session = Depends(get_db)) -> ActivityRepo:
    """Репозиторий активностей."""
    return ActivityRepo(session)


def get_hotkeys_repo(session: Session = Depends(get_db)) -> HotkeysRepo:
    """Репозиторий hotkey-кнопок."""
    return HotkeysRepo(session)


def get_logs_repo(session: Session = Depends(get_db)) -> LogsRepo:
    """Репозиторий логов."""
    return LogsRepo(session)


def get_sessions_repo(session: Session = Depends(get_db)) -> SessionsRepo:
    """Репозиторий сессий."""
    return SessionsRepo(session)


def get_users_repo(session: Session = Depends(get_db)) -> UsersRepo:
    """Репозиторий пользователей."""
    return UsersRepo(session)