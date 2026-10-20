from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002_add_analytics_events"
down_revision: Union[str, None] = "001_initial_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "click_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=512), server_default="", nullable=False),
        sa.Column("referrer", sa.String(length=1024), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_click_events_link_id"), "click_events", ["link_id"], unique=False)
    op.create_index(op.f("ix_click_events_created_at"), "click_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_click_events_created_at"), table_name="click_events")
    op.drop_index(op.f("ix_click_events_link_id"), table_name="click_events")
    op.drop_table("click_events")
