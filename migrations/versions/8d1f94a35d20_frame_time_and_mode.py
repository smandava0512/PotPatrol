"""Store optional first-frame wall time, hazard observation time, and analyzer mode.

Revision ID: 8d1f94a35d20
Revises: aa240d92facf
"""
from alembic import op
import sqlalchemy as sa

revision = "8d1f94a35d20"
down_revision = "aa240d92facf"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("drives", sa.Column("video_started_at", sa.String(length=40), nullable=True))
    op.add_column("drives", sa.Column("analysis_mode", sa.String(length=20), nullable=True))
    op.add_column("hazards", sa.Column("observed_at", sa.String(length=40), nullable=True))


def downgrade():
    op.drop_column("hazards", "observed_at")
    op.drop_column("drives", "analysis_mode")
    op.drop_column("drives", "video_started_at")
