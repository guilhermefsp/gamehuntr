"""add ludopedia_link to games and ludopedia_listings table

Revision ID: 0001
Revises:
Create Date: 2026-04-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = "0000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("ludopedia_link", sa.String(512), nullable=True))

    op.create_table(
        "ludopedia_listings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("listing_url", sa.String(1024), nullable=False),
        sa.Column("product_name", sa.String(256), nullable=False),
        sa.Column("city", sa.String(128), nullable=True),
        sa.Column("price_brl", sa.Numeric(10, 2), nullable=True),
        sa.Column("condition", sa.String(64), nullable=True),
        sa.Column("notes", sa.String(512), nullable=True),
        sa.Column("is_game_match", sa.Boolean(), nullable=False),
        sa.Column("scraped_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.ludopedia_id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ludopedia_listings")
    op.drop_column("games", "ludopedia_link")
