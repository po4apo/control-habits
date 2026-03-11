"""Модели SQLAlchemy 2.x для всех таблиц БД (PostgreSQL, даты/время в UTC)."""

from datetime import datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Time,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, SMALLINT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""

    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class User(Base):
    """Пользователь (идентификация по Telegram)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} telegram_user_id={self.telegram_user_id}>"


class LinkCode(Base):
    """Одноразовый код привязки веб-сессии к Telegram."""

    __tablename__ = "link_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    web_session_id: Mapped[str] = mapped_column(String(256), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    def __repr__(self) -> str:
        return f"<LinkCode code={self.code!r} consumed={self.consumed_at is not None}>"


class Activity(Base):
    """Активность пользователя (hotkey или regular)."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # hotkey | regular

    def __repr__(self) -> str:
        return f"<Activity id={self.id} name={self.name!r}>"


class Hotkey(Base):
    """Быстрая кнопка: связь пользователя и активности с подписью и порядком."""

    __tablename__ = "hotkeys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("activities.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    order: Mapped[int] = mapped_column(nullable=False)

    def __repr__(self) -> str:
        return f"<Hotkey id={self.id} label={self.label!r}>"


class ScheduleTemplate(Base):
    """Шаблон расписания пользователя."""

    __tablename__ = "schedule_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)

    def __repr__(self) -> str:
        return f"<ScheduleTemplate id={self.id} name={self.name!r}>"


class PlanItem(Base):
    """Элемент плана в шаблоне (task или event)."""

    __tablename__ = "plan_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("schedule_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # task | event
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    days_of_week: Mapped[list[int]] = mapped_column(
        ARRAY(SMALLINT), nullable=False
    )  # 1–7
    activity_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<PlanItem id={self.id} kind={self.kind} title={self.title!r}>"


class Notification(Base):
    """Запланированная отправка пуша (planned_at в UTC)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("plan_items.id", ondelete="CASCADE"), nullable=False
    )
    planned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # task_prompt | event_start | event_end
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(256), unique=True, nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<Notification id={self.id} planned_at={self.planned_at} sent_at={self.sent_at}>"


class LogEntry(Base):
    """Факт ответа/действия пользователя (времена в UTC)."""

    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plan_items.id", ondelete="SET NULL"), nullable=True
    )
    activity_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )
    planned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    responded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<LogEntry id={self.id} action={self.action}>"


class TimeSegment(Base):
    """Временной отрезок трекинга: старт/стоп активности (hotkey или запланированное событие)."""

    __tablename__ = "time_segments"

    __table_args__ = (
        Index(
            "ix_time_segments_user_activity_ended",
            "user_id",
            "activity_id",
            "ended_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("activities.id", ondelete="CASCADE"), nullable=False
    )
    plan_item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plan_items.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<TimeSegment id={self.id} user_id={self.user_id} activity_id={self.activity_id}>"


class BugReportDraft(Base):
    """Черновик баг-репорта: состояние диалога и описание до отправки в GitHub."""

    __tablename__ = "bug_report_drafts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(4096), nullable=False)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # waiting_description | waiting_confirm | sent | cancelled
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    github_issue_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:
        return f"<BugReportDraft id={self.id} state={self.state}>"
