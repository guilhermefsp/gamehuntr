"""add bgg_rating, bgg_weight, bgg_synced_at to games

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("bgg_rating", sa.Numeric(4, 2), nullable=True))
    op.add_column("games", sa.Column("bgg_weight", sa.Numeric(4, 2), nullable=True))
    op.add_column("games", sa.Column("bgg_synced_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("games", "bgg_synced_at")
    op.drop_column("games", "bgg_weight")
    op.drop_column("games", "bgg_rating")
