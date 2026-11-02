"""allow asr processing stage

Revision ID: 70e6de9a9544
Revises: d9fbf5fd4892
Create Date: 2026-11-02 09:19:42.060430+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "70e6de9a9544"
down_revision: str | None = "d9fbf5fd4892"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_processing_stages_name"), "processing_stages", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_processing_stages_name"),
        "processing_stages",
        "name IN ('vad', 'asr')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM processing_stages WHERE name = 'asr'")
    op.drop_constraint(
        op.f("ck_processing_stages_name"), "processing_stages", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_processing_stages_name"),
        "processing_stages",
        "name IN ('vad')",
    )
