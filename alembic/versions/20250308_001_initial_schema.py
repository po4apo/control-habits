"""Начальная схема: users, link_codes, activities, hotkeys, schedule_templates, plan_items, notifications, log_entries, active_sessions.

Revision ID: 001
Revises:
Create Date: 2025-03-08

Все даты/времена в БД — UTC (TIMESTAMP WITH TIME ZONE).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_users_telegram_user_id"), "users", ["telegram_user_id"], unique=True
    )

    op.create_table(
        "link_codes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("web_session_id", sa.String(length=256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_link_codes_code"), "link_codes", ["code"], unique=True)

    op.create_table(
        "activities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_activities_user_id"), "activities", ["user_id"], unique=False)

    op.create_table(
        "schedule_templates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_schedule_templates_user_id"),
        "schedule_templates",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "hotkeys",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_hotkeys_user_id"), "hotkeys", ["user_id"], unique=False)

    op.create_table(
        "plan_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column(
            "days_of_week",
            postgresql.ARRAY(sa.SMALLINT()),
            nullable=False,
        ),
        sa.Column("activity_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["activity_id"], ["activities.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["schedule_templates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_item_id", sa.BigInteger(), nullable=False),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.ForeignKeyConstraint(["plan_item_id"], ["plan_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_notifications_planned_at"), "notifications", ["planned_at"], unique=False
    )
    op.create_index(
        op.f("ix_notifications_sent_at"), "notifications", ["sent_at"], unique=False
    )
    op.create_index(
        op.f("ix_notifications_idempotency_key"),
        "notifications",
        ["idempotency_key"],
        unique=True,
    )

    op.create_table(
        "log_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_item_id", sa.BigInteger(), nullable=True),
        sa.Column("activity_id", sa.BigInteger(), nullable=True),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_item_id"], ["plan_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_log_entries_user_id"), "log_entries", ["user_id"], unique=False
    )

    op.create_table(
        "active_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_active_sessions_user_id"),
        "active_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_active_sessions_user_activity_ended",
        "active_sessions",
        ["user_id", "activity_id", "ended_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_active_sessions_user_activity_ended",
        table_name="active_sessions",
    )
    op.drop_index(
        op.f("ix_active_sessions_user_id"), table_name="active_sessions"
    )
    op.drop_table("active_sessions")

    op.drop_index(op.f("ix_log_entries_user_id"), table_name="log_entries")
    op.drop_table("log_entries")

    op.drop_index(
        op.f("ix_notifications_idempotency_key"), table_name="notifications"
    )
    op.drop_index(op.f("ix_notifications_sent_at"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_planned_at"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_table("notifications")

    op.drop_table("plan_items")

    op.drop_index(op.f("ix_hotkeys_user_id"), table_name="hotkeys")
    op.drop_table("hotkeys")

    op.drop_index(
        op.f("ix_schedule_templates_user_id"), table_name="schedule_templates"
    )
    op.drop_table("schedule_templates")

    op.drop_index(op.f("ix_activities_user_id"), table_name="activities")
    op.drop_table("activities")

    op.drop_index(op.f("ix_link_codes_code"), table_name="link_codes")
    op.drop_table("link_codes")

    op.drop_index(op.f("ix_users_telegram_user_id"), table_name="users")
    op.drop_table("users")
