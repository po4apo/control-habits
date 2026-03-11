"""Репозиторий временных отрезков (TimeSegment)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_habits.storage.models import TimeSegment


class TimeSegmentRepo:
    """Доступ к временным отрезкам. Все времена в UTC."""

    def __init__(self, session: Session) -> None:
        """
        :param session: Сессия SQLAlchemy.
        """
        self._session = session

    def create(
        self,
        user_id: int,
        activity_id: int,
        started_at: datetime,
        plan_item_id: int | None = None,
    ) -> TimeSegment:
        """
        Создать временной отрезок (открытый, ended_at=NULL).

        :param user_id: Идентификатор пользователя.
        :param activity_id: Идентификатор активности.
        :param started_at: Время старта (UTC).
        :param plan_item_id: Опционально — элемент плана (запланированное событие).
        :returns: Созданная модель TimeSegment.
        """
        segment = TimeSegment(
            user_id=user_id,
            activity_id=activity_id,
            plan_item_id=plan_item_id,
            started_at=started_at,
        )
        self._session.add(segment)
        self._session.flush()
        return segment

    def get_by_id(self, segment_id: int) -> TimeSegment | None:
        """
        Найти отрезок по идентификатору.

        :param segment_id: Идентификатор отрезка.
        :returns: TimeSegment или None.
        """
        return self._session.get(TimeSegment, segment_id)

    def get_open(
        self,
        user_id: int,
        activity_id: int,
        plan_item_id: int | None = None,
    ) -> TimeSegment | None:
        """
        Найти открытый отрезок (ended_at IS NULL) по пользователю и активности.

        Для hotkey: plan_item_id=None. Для запланированного: можно фильтровать по plan_item_id.

        :param user_id: Идентификатор пользователя.
        :param activity_id: Идентификатор активности.
        :param plan_item_id: Опционально — фильтр по элементу плана.
        :returns: TimeSegment или None.
        """
        stmt = (
            select(TimeSegment)
            .where(TimeSegment.user_id == user_id)
            .where(TimeSegment.activity_id == activity_id)
            .where(TimeSegment.ended_at.is_(None))
        )
        if plan_item_id is not None:
            stmt = stmt.where(TimeSegment.plan_item_id == plan_item_id)
        return self._session.scalar(stmt.limit(1))

    def get_open_by_plan_item(
        self,
        user_id: int,
        plan_item_id: int,
    ) -> TimeSegment | None:
        """
        Найти открытый отрезок по plan_item_id.

        :param user_id: Идентификатор пользователя.
        :param plan_item_id: Идентификатор элемента плана.
        :returns: TimeSegment или None.
        """
        stmt = (
            select(TimeSegment)
            .where(TimeSegment.user_id == user_id)
            .where(TimeSegment.plan_item_id == plan_item_id)
            .where(TimeSegment.ended_at.is_(None))
            .limit(1)
        )
        return self._session.scalar(stmt)

    def list_open(self, user_id: int) -> list[TimeSegment]:
        """
        Список всех открытых отрезков пользователя (ended_at IS NULL).

        :param user_id: Идентификатор пользователя.
        :returns: Список TimeSegment.
        """
        stmt = (
            select(TimeSegment)
            .where(TimeSegment.user_id == user_id)
            .where(TimeSegment.ended_at.is_(None))
            .order_by(TimeSegment.started_at)
        )
        return list(self._session.scalars(stmt).all())

    def close(self, segment_id: int, ended_at: datetime) -> None:
        """
        Закрыть отрезок: установить ended_at.

        :param segment_id: Идентификатор отрезка.
        :param ended_at: Время окончания (UTC).
        """
        segment = self._session.get(TimeSegment, segment_id)
        if segment is not None:
            segment.ended_at = ended_at
            self._session.flush()

    def list_segments_in_range(
        self,
        user_id: int,
        utc_from: datetime,
        utc_to: datetime,
        activity_id: int | None = None,
    ) -> list[TimeSegment]:
        """
        Закрытые отрезки пользователя, пересекающиеся с UTC-интервалом [utc_from, utc_to].

        Учитываются отрезки, у которых (started_at, ended_at) пересекается с интервалом:
        started_at < utc_to и ended_at >= utc_from.

        :param user_id: Идентификатор пользователя.
        :param utc_from: Начало интервала (UTC).
        :param utc_to: Конец интервала (UTC).
        :param activity_id: Опционально — фильтр по активности.
        :returns: Список TimeSegment с заполненным ended_at, по started_at.
        """
        stmt = (
            select(TimeSegment)
            .where(TimeSegment.user_id == user_id)
            .where(TimeSegment.ended_at.is_not(None))
            .where(TimeSegment.started_at < utc_to)
            .where(TimeSegment.ended_at >= utc_from)
        )
        if activity_id is not None:
            stmt = stmt.where(TimeSegment.activity_id == activity_id)
        stmt = stmt.order_by(TimeSegment.started_at)
        return list(self._session.scalars(stmt).all())

    def has_open_segment(
        self,
        user_id: int,
        activity_id: int,
        plan_item_id: int | None = None,
    ) -> bool:
        """
        Есть ли открытый отрезок для данной активности.

        :param user_id: Идентификатор пользователя.
        :param activity_id: Идентификатор активности.
        :param plan_item_id: Опционально — фильтр по элементу плана.
        :returns: True, если есть открытый отрезок.
        """
        return self.get_open(user_id, activity_id, plan_item_id) is not None

    # Алиасы для совместимости с прежним SessionsRepo API
    def get_active(self, user_id: int, activity_id: int) -> TimeSegment | None:
        """Алиас get_open для hotkey (plan_item_id=None)."""
        return self.get_open(user_id, activity_id, None)

    def list_active(self, user_id: int) -> list[TimeSegment]:
        """Алиас list_open."""
        return self.list_open(user_id)

    def list_closed_in_range(
        self,
        user_id: int,
        utc_from: datetime,
        utc_to: datetime,
    ) -> list[TimeSegment]:
        """Алиас list_segments_in_range без фильтра по activity_id."""
        return self.list_segments_in_range(user_id, utc_from, utc_to)


# Обратная совместимость
SessionsRepo = TimeSegmentRepo
