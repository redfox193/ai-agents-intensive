"""initial links table

Revision ID: 001_initial_links
Revises:
Create Date: 2026-09-21 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_initial_links"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("short_code", sa.String(length=16), nullable=False),
        sa.Column("target_url", sa.String(length=2048), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_links_short_code"), "links", ["short_code"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_links_short_code"), table_name="links")
    op.drop_table("links")
