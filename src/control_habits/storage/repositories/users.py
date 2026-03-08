"""Репозиторий пользователей."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_habits.storage.models import User


class UsersRepo:
    """Доступ к пользователям. Все времена в UTC."""

    def __init__(self, session: Session) -> None:
        """
        :param session: Сессия SQLAlchemy.
        """
        self._session = session

    def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        """
        Найти пользователя по Telegram ID.

        :param telegram_user_id: Идентификатор пользователя в Telegram.
        :returns: Пользователь или None.
        """
        stmt = select(User).where(User.telegram_user_id == telegram_user_id)
        return self._session.scalar(stmt)

    def get_by_id(self, user_id: int) -> User | None:
        """
        Найти пользователя по внутреннему id.

        :param user_id: Внутренний идентификатор пользователя.
        :returns: Пользователь или None.
        """
        return self._session.get(User, user_id)

    def create(
        self,
        telegram_user_id: int,
        timezone: str,
        created_at: datetime | None = None,
    ) -> User:
        """
        Создать пользователя.

        :param telegram_user_id: Идентификатор в Telegram.
        :param timezone: IANA timezone (например Europe/Moscow).
        :param created_at: Время создания (UTC); если None — вызывающий задаёт снаружи.
        :returns: Созданная модель User.
        """
        if created_at is None:
            created_at = datetime.now(timezone.utc)
        user = User(
            telegram_user_id=telegram_user_id,
            timezone=timezone,
            created_at=created_at,
        )
        self._session.add(user)
        self._session.flush()
        return user

    def update_timezone(self, user_id: int, timezone: str) -> None:
        """
        Обновить часовой пояс пользователя.

        :param user_id: Идентификатор пользователя.
        :param timezone: Новое значение IANA timezone.
        """
        user = self._session.get(User, user_id)
        if user is not None:
            user.timezone = timezone
