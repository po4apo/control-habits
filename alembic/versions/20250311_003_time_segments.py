"""TimeSegment: замена active_sessions на time_segments.

Revision ID: 003
Revises: 002
Create Date: 2025-03-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "time_segments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_item_id", sa.BigInteger(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["plan_item_id"], ["plan_items.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_time_segments_user_id"),
        "time_segments",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_time_segments_user_activity_ended",
        "time_segments",
        ["user_id", "activity_id", "ended_at"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            INSERT INTO time_segments (user_id, activity_id, plan_item_id, started_at, ended_at)
            SELECT user_id, activity_id, NULL, started_at, ended_at
            FROM active_sessions
            """
        )
    )

    op.drop_index(
        "ix_active_sessions_user_activity_ended",
        table_name="active_sessions",
    )
    op.drop_index(
        op.f("ix_active_sessions_user_id"),
        table_name="active_sessions",
    )
    op.drop_table("active_sessions")


def downgrade() -> None:
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

    op.execute(
        sa.text(
            """
            INSERT INTO active_sessions (user_id, activity_id, started_at, ended_at)
            SELECT user_id, activity_id, started_at, ended_at
            FROM time_segments
            WHERE plan_item_id IS NULL
            """
        )
    )

    op.drop_index(
        "ix_time_segments_user_activity_ended",
        table_name="time_segments",
    )
    op.drop_index(
        op.f("ix_time_segments_user_id"),
        table_name="time_segments",
    )
    op.drop_table("time_segments")
