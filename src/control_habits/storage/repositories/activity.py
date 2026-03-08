"""Репозиторий активностей."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_habits.storage.models import Activity


class ActivityRepo:
    """Доступ к активностям пользователя."""

    def __init__(self, session: Session) -> None:
        """
        :param session: Сессия SQLAlchemy.
        """
        self._session = session

    def list_by_user(self, user_id: int) -> list[Activity]:
        """
        Список активностей пользователя.

        :param user_id: Идентификатор пользователя.
        :returns: Список активностей (по id).
        """
        stmt = (
            select(Activity)
            .where(Activity.user_id == user_id)
            .order_by(Activity.id)
        )
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, activity_id: int) -> Activity | None:
        """
        Найти активность по id.

        :param activity_id: Идентификатор активности.
        :returns: Activity или None.
        """
        return self._session.get(Activity, activity_id)

    def create(self, user_id: int, name: str, kind: str) -> Activity:
        """
        Создать активность.

        :param user_id: Идентификатор пользователя.
        :param name: Название активности.
        :param kind: Тип: hotkey или regular.
        :returns: Созданная модель Activity.
        """
        activity = Activity(
            user_id=user_id,
            name=name,
            kind=kind,
        )
        self._session.add(activity)
        self._session.flush()
        return activity

    def delete(self, activity_id: int) -> None:
        """
        Удалить активность по id.

        :param activity_id: Идентификатор активности.
        """
        activity = self._session.get(Activity, activity_id)
        if activity is not None:
            self._session.delete(activity)
