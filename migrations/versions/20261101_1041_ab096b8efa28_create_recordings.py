"""create recordings

Revision ID: ab096b8efa28
Revises:
Create Date: 2026-11-01 10:41:21.723785+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ab096b8efa28"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recordings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("part_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("upload_id", sa.Text(), nullable=True),
        sa.Column("etag", sa.String(length=128), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending_upload', 'uploaded', 'aborted', 'failed')",
            name=op.f("ck_recordings_status"),
        ),
        sa.CheckConstraint(
            "part_size_bytes > 0", name=op.f("ck_recordings_part_size_positive")
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_recordings_size_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recordings")),
        sa.UniqueConstraint("object_key", name=op.f("uq_recordings_object_key")),
    )
    op.create_index(
        "ix_recordings_owner_id_created_at",
        "recordings",
        ["owner_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_recordings_owner_id_created_at", table_name="recordings")
    op.drop_table("recordings")
