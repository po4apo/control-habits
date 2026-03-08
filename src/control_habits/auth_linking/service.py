"""Сервис привязки: выдача и потребление одноразовых кодов."""

import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from control_habits.storage.repositories.link_codes import LinkCodesRepo
from control_habits.storage.repositories.users import UsersRepo

LinkStatus = Literal["pending", "consumed", "expired", "not_found"]
ConsumeFailReason = Literal["expired", "already_used", "not_found"]


@dataclass
class ConsumeLinkResult:
    """Результат потребления кода привязки."""

    success: bool
    user_id: int | None = None
    reason: ConsumeFailReason | None = None


# Символы кода по спекам: A–Z, a–z, 0–9, _, -
_CODE_ALPHABET = string.ascii_letters + string.digits + "_" + "-"
_CODE_LENGTH = 24


class AuthLinkingService:
    """Выдача и потребление кодов привязки веб-сессии к Telegram."""

    def __init__(
        self,
        link_codes_repo: LinkCodesRepo,
        users_repo: UsersRepo,
        *,
        default_timezone: str = "UTC",
    ) -> None:
        """
        :param link_codes_repo: Репозиторий кодов привязки.
        :param users_repo: Репозиторий пользователей.
        :param default_timezone: IANA timezone для вновь создаваемых пользователей.
        """
        self._link_codes = link_codes_repo
        self._users = users_repo
        self._default_timezone = default_timezone

    def create_link_code(
        self,
        web_session_id: str,
        ttl_seconds: int = 600,
    ) -> str:
        """
        Создать одноразовый код привязки и сохранить в БД.

        Код содержит только символы A–Z, a–z, 0–9, _, -. Срок действия задаётся TTL.

        :param web_session_id: Идентификатор веб-сессии.
        :param ttl_seconds: Время жизни кода в секундах (по умолчанию 600).
        :returns: Сгенерированный код.
        """
        code = "".join(
            secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH)
        )
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self._link_codes.create(
            code=code,
            web_session_id=web_session_id,
            expires_at=expires_at,
        )
        return code

    def get_link_status(self, code: str) -> LinkStatus:
        """
        Получить статус кода привязки (для polling со стороны фронта).

        :param code: Строка кода.
        :returns: pending | consumed | expired | not_found.
        """
        link = self._link_codes.get_by_code(code)
        if link is None:
            return "not_found"
        if link.consumed_at is not None:
            return "consumed"
        now = datetime.now(timezone.utc)
        if link.expires_at < now:
            return "expired"
        return "pending"

    def get_link_status_by_session(
        self, web_session_id: str
    ) -> tuple[LinkStatus, str | None]:
        """
        Получить статус привязки по идентификатору веб-сессии (последний созданный код).

        :param web_session_id: Идентификатор веб-сессии.
        :returns: Пара (статус, код или None если кода нет).
        """
        link = self._link_codes.get_latest_by_web_session_id(web_session_id)
        if link is None:
            return "not_found", None
        return self.get_link_status(link.code), link.code

    def get_user_id_by_web_session(self, web_session_id: str) -> int | None:
        """
        Получить user_id по привязанной веб-сессии (последний consumed код).

        :param web_session_id: Идентификатор веб-сессии.
        :returns: Идентификатор пользователя или None, если сессия не привязана.
        """
        link = self._link_codes.get_latest_by_web_session_id(web_session_id)
        if link is None or link.consumed_at is None or link.telegram_user_id is None:
            return None
        user = self._users.get_by_telegram_id(link.telegram_user_id)
        return user.id if user else None

    def consume_link_code(
        self,
        code: str,
        telegram_user_id: int,
    ) -> ConsumeLinkResult:
        """
        Потребить код привязки: пометить использованным и вернуть результат.

        Если код не найден, истёк или уже использован — возвращается результат с reason.
        Иначе код помечается использованным, связывается с telegram_user_id;
        пользователь создаётся при отсутствии. Один код — одно потребление.

        :param code: Строка кода.
        :param telegram_user_id: Идентификатор пользователя в Telegram.
        :returns: ConsumeLinkResult (success + user_id или reason).
        """
        link = self._link_codes.get_by_code(code)
        if link is None:
            return ConsumeLinkResult(success=False, reason="not_found")
        if link.consumed_at is not None:
            return ConsumeLinkResult(success=False, reason="already_used")
        now = datetime.now(timezone.utc)
        if link.expires_at < now:
            return ConsumeLinkResult(success=False, reason="expired")

        self._link_codes.mark_consumed(code, telegram_user_id, consumed_at=now)

        user = self._users.get_by_telegram_id(telegram_user_id)
        if user is None:
            user = self._users.create(
                telegram_user_id=telegram_user_id,
                timezone=self._default_timezone,
                created_at=now,
            )
        return ConsumeLinkResult(success=True, user_id=user.id)
