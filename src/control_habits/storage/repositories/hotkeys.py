"""Репозиторий горячих кнопок (hotkeys)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_habits.storage.models import Hotkey


class HotkeysRepo:
    """Доступ к hotkey-кнопкам пользователя."""

    def __init__(self, session: Session) -> None:
        """
        :param session: Сессия SQLAlchemy.
        """
        self._session = session

    def list_by_user(self, user_id: int) -> list[Hotkey]:
        """
        Список hotkey пользователя, отсортированный по полю order.

        :param user_id: Идентификатор пользователя.
        :returns: Список Hotkey.
        """
        stmt = (
            select(Hotkey)
            .where(Hotkey.user_id == user_id)
            .order_by(Hotkey.order, Hotkey.id)
        )
        return list(self._session.scalars(stmt).all())

    def add(
        self,
        user_id: int,
        activity_id: int,
        label: str,
        order: int,
    ) -> Hotkey:
        """
        Добавить hotkey.

        :param user_id: Идентификатор пользователя.
        :param activity_id: Идентификатор активности.
        :param label: Подпись на кнопке.
        :param order: Порядок отображения.
        :returns: Созданная модель Hotkey.
        """
        hotkey = Hotkey(
            user_id=user_id,
            activity_id=activity_id,
            label=label,
            order=order,
        )
        self._session.add(hotkey)
        self._session.flush()
        return hotkey

    def remove(self, hotkey_id: int) -> None:
        """
        Удалить hotkey по id.

        :param hotkey_id: Идентификатор записи hotkey.
        """
        hotkey = self._session.get(Hotkey, hotkey_id)
        if hotkey is not None:
            self._session.delete(hotkey)

    def reorder(self, user_id: int, hotkey_ids_in_order: list[int]) -> None:
        """
        Задать новый порядок hotkey: order = позиция в списке.

        :param user_id: Идентификатор пользователя (проверка владения).
        :param hotkey_ids_in_order: Список id hotkey в нужном порядке (индекс = order).
        """
        for order, hotkey_id in enumerate(hotkey_ids_in_order):
            hotkey = self._session.get(Hotkey, hotkey_id)
            if hotkey is not None and hotkey.user_id == user_id:
                hotkey.order = order
