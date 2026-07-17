"""Drop lorebook tables with the removed lorebook/dashboard surface.

Deletion notes:
- The lorebook + dashboard HTTP surface, `LoreManager`, and the `LoreEntry` /
  `LoreKey` ORM models were removed: generation stopped reading lorebook
  context earlier, and the routes had no first-party callers left.
- `lore_keys` and `lore_entries` are dropped (in FK order). Lorebook rows are
  user-entered data; deployments that need them must back up before upgrading.

Rollback:
- `alembic downgrade 037` restores empty tables (data is not restored)
- `git revert <commit>`
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "lore_keys" in tables:
        op.drop_table("lore_keys")
    if "lore_entries" in tables:
        op.drop_table("lore_entries")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "lore_entries" not in tables:
        op.create_table(
            "lore_entries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("novel_id", sa.Integer(), sa.ForeignKey("novels.id"), nullable=False),
            sa.Column("uid", sa.String(length=36), nullable=False, unique=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("entry_type", sa.String(length=50), nullable=False),
            sa.Column("token_budget", sa.Integer()),
            sa.Column("priority", sa.Integer()),
            sa.Column("enabled", sa.Boolean()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )
    if "lore_keys" not in tables:
        op.create_table(
            "lore_keys",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("entry_id", sa.Integer(), sa.ForeignKey("lore_entries.id"), nullable=False),
            sa.Column("keyword", sa.String(length=255), nullable=False),
            sa.Column("is_regex", sa.Boolean()),
            sa.Column("case_sensitive", sa.Boolean()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
