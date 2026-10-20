from typing import Sequence, Union
from alembic import op

revision: str = "003_add_created_at_idx"
down_revision: Union[str, None] = "002_add_analytics_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_index("ix_links_created_at", "links", ["created_at"], unique=False)

def downgrade() -> None:
    op.drop_index("ix_links_created_at", table_name="links")
