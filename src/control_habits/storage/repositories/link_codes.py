"""Репозиторий кодов привязки."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_habits.storage.models import LinkCode


class LinkCodesRepo:
    """Доступ к одноразовым кодам привязки. Все времена в UTC."""

    def __init__(self, session: Session) -> None:
        """
        :param session: Сессия SQLAlchemy.
        """
        self._session = session

    def create(
        self,
        code: str,
        web_session_id: str,
        expires_at: datetime,
    ) -> LinkCode:
        """
        Создать код привязки.

        :param code: Уникальный код (символы A–Z, a–z, 0–9, _, -).
        :param web_session_id: Идентификатор веб-сессии.
        :param expires_at: Время истечения (UTC).
        :returns: Созданная модель LinkCode.
        """
        link_code = LinkCode(
            code=code,
            web_session_id=web_session_id,
            expires_at=expires_at,
        )
        self._session.add(link_code)
        self._session.flush()
        return link_code

    def get_by_code(self, code: str) -> LinkCode | None:
        """
        Найти код по значению.

        :param code: Строка кода.
        :returns: LinkCode или None.
        """
        stmt = select(LinkCode).where(LinkCode.code == code)
        return self._session.scalar(stmt)

    def get_latest_by_web_session_id(self, web_session_id: str) -> LinkCode | None:
        """
        Найти последний код по идентификатору веб-сессии (для проверки статуса при polling).

        :param web_session_id: Идентификатор веб-сессии.
        :returns: Последний созданный LinkCode для этой сессии или None.
        """
        stmt = (
            select(LinkCode)
            .where(LinkCode.web_session_id == web_session_id)
            .order_by(LinkCode.id.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def mark_consumed(
        self,
        code: str,
        telegram_user_id: int,
        consumed_at: datetime | None = None,
    ) -> None:
        """
        Пометить код использованным и сохранить telegram_user_id.

        :param code: Строка кода.
        :param telegram_user_id: Идентификатор пользователя в Telegram.
        :param consumed_at: Время потребления (UTC); если None — вызывающий задаёт снаружи.
        """
        link_code = self.get_by_code(code)
        if link_code is None:
            return
        if consumed_at is None:
            consumed_at = datetime.now(timezone.utc)
        link_code.consumed_at = consumed_at
        link_code.telegram_user_id = telegram_user_id
