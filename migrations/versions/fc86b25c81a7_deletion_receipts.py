"""Persist opaque owner-bound deletion receipts.

Revision ID: fc86b25c81a7
Revises: c8e0a12451d6
"""
from alembic import op
import sqlalchemy as sa

revision = "fc86b25c81a7"
down_revision = "c8e0a12451d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("deletion_receipts", sa.Column("digest", sa.String(length=64), primary_key=True))


def downgrade():
    op.drop_table("deletion_receipts")
