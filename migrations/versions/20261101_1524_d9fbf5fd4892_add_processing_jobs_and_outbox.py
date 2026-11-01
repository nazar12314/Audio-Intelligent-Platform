"""add processing jobs and outbox

Revision ID: d9fbf5fd4892
Revises: b7f8ff46db4a
Create Date: 2026-11-01 15:24:52.579867+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d9fbf5fd4892"
down_revision: str | None = "b7f8ff46db4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("destination", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
    )
    op.create_index(
        "ix_outbox_pending",
        "outbox",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recording_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("speech_detected", sa.Boolean(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name=op.f("ck_processing_jobs_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_jobs")),
        sa.UniqueConstraint("recording_id", name=op.f("uq_processing_jobs_recording_id")),
    )
    op.create_table(
        "processing_stages",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("name IN ('vad')", name=op.f("ck_processing_stages_name")),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name=op.f("ck_processing_stages_status"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["processing_jobs.id"],
            name=op.f("fk_processing_stages_job_id_processing_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", "name", name=op.f("pk_processing_stages")),
    )


def downgrade() -> None:
    op.drop_table("processing_stages")
    op.drop_table("processing_jobs")
    op.drop_index("ix_outbox_pending", table_name="outbox")
    op.drop_table("outbox")
