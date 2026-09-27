"""Fence job attempts with a private claim token.

Revision ID: c8e0a12451d6
Revises: 8d1f94a35d20
"""
from alembic import op
import sqlalchemy as sa

revision = "c8e0a12451d6"
down_revision = "8d1f94a35d20"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("claim_token", sa.String(length=36), nullable=True))


def downgrade():
    op.drop_column("jobs", "claim_token")
