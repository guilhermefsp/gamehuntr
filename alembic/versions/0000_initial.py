"""initial schema

Revision ID: 0000
Revises:
Create Date: 2026-04-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("ludopedia_id", sa.Integer(), nullable=False),
        sa.Column("bgg_id", sa.Integer(), nullable=True),
        sa.Column("asin", sa.String(16), nullable=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("thumbnail", sa.String(512), nullable=True),
        sa.Column("min_players", sa.Integer(), nullable=True),
        sa.Column("max_players", sa.Integer(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("qt_quer", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("ludopedia_id"),
        sa.UniqueConstraint("bgg_id"),
        sa.UniqueConstraint("asin"),
    )
    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("base_url", sa.String(256), nullable=False),
        sa.Column("affiliate_tag", sa.String(128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("price_brl", sa.Numeric(10, 2), nullable=True),
        sa.Column("in_stock", sa.Boolean(), nullable=False),
        sa.Column("scraped_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.ludopedia_id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "price_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("price_brl", sa.Numeric(10, 2), nullable=True),
        sa.Column("in_stock", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("price_history")
    op.drop_table("listings")
    op.drop_table("stores")
    op.drop_table("games")
