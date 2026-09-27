"""Persist bounded drive and hazard vision provenance.

Revision ID: ba902f73c819
Revises: fc86b25c81a7
"""
from alembic import op
import sqlalchemy as sa

revision = "ba902f73c819"
down_revision = "fc86b25c81a7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("drives", sa.Column("vision_mode", sa.String(length=30), nullable=True))
    op.add_column("drives", sa.Column("validator_model", sa.String(length=100), nullable=True))
    op.add_column("drives", sa.Column("gemini_frames_scanned", sa.Integer(), nullable=True))
    op.add_column("hazards", sa.Column("source", sa.String(length=40), nullable=True))
    op.add_column("hazards", sa.Column("validation", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("hazards", "validation")
    op.drop_column("hazards", "source")
    op.drop_column("drives", "gemini_frames_scanned")
    op.drop_column("drives", "validator_model")
    op.drop_column("drives", "vision_mode")
