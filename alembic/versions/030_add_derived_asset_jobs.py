"""Add derived-asset job seam table.

Deletion notes:
- Replaces the feature-local window-index rebuild lock/orchestration path with a
  durable shared job row per `(novel_id, asset_kind)`.

Rollback:
- `alembic downgrade 029`
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "derived_asset_jobs" in tables:
        return

    op.create_table(
        "derived_asset_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("novel_id", sa.Integer(), nullable=False),
        sa.Column("asset_kind", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("target_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_revision", sa.Integer(), nullable=True),
        sa.Column("completed_revision", sa.Integer(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("novel_id", "asset_kind", name="uq_derived_asset_jobs_novel_asset_kind"),
    )
    op.create_index(
        "ix_derived_asset_jobs_status_lease",
        "derived_asset_jobs",
        ["status", "lease_expires_at"],
        unique=False,
    )

    dialect = bind.dialect.name if bind is not None else ""
    if dialect == "sqlite":
        with op.batch_alter_table("derived_asset_jobs") as batch_op:
            batch_op.alter_column("status", server_default=None)
            batch_op.alter_column("target_revision", server_default=None)
    else:
        op.alter_column("derived_asset_jobs", "status", server_default=None)
        op.alter_column("derived_asset_jobs", "target_revision", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "derived_asset_jobs" not in tables:
        return

    indexes = {index["name"] for index in inspector.get_indexes("derived_asset_jobs")}
    if "ix_derived_asset_jobs_status_lease" in indexes:
        op.drop_index("ix_derived_asset_jobs_status_lease", table_name="derived_asset_jobs")
    op.drop_table("derived_asset_jobs")
