"""Таблица черновиков баг-репортов: bug_report_drafts.

Revision ID: 002
Revises: 001
Create Date: 2025-03-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bug_report_drafts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(length=4096), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("github_issue_url", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bug_report_drafts_telegram_user_id"),
        "bug_report_drafts",
        ["telegram_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bug_report_drafts_user_id"),
        "bug_report_drafts",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_bug_report_drafts_user_id"), table_name="bug_report_drafts"
    )
    op.drop_index(
        op.f("ix_bug_report_drafts_telegram_user_id"),
        table_name="bug_report_drafts",
    )
    op.drop_table("bug_report_drafts")
