"""index recordings by owner and id

Revision ID: b7f8ff46db4a
Revises: ab096b8efa28
Create Date: 2026-11-01 11:19:30.602977+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7f8ff46db4a"
down_revision: str | None = "ab096b8efa28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_recordings_owner_id_id", "recordings", ["owner_id", "id"], unique=False
    )
    op.drop_index("ix_recordings_owner_id_created_at", table_name="recordings")


def downgrade() -> None:
    op.create_index(
        "ix_recordings_owner_id_created_at",
        "recordings",
        ["owner_id", "created_at"],
        unique=False,
    )
    op.drop_index("ix_recordings_owner_id_id", table_name="recordings")
