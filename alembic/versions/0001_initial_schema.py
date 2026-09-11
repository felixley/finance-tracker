"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-11

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bank_name", sa.String(100), nullable=False),
        sa.Column("iban", sa.String(34), nullable=False),
        sa.Column("balance", sa.Numeric(14, 2), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(255), nullable=False, unique=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("buchungsdatum", sa.Date(), nullable=False),
        sa.Column("valutadatum", sa.Date(), nullable=True),
        sa.Column("betrag", sa.Numeric(14, 2), nullable=False),
        sa.Column("waehrung", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("partner_name", sa.Text(), nullable=True),
        sa.Column("verwendungszweck", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pattern", sa.String(255), nullable=False),
        sa.Column("match_field", sa.String(30), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_from_manual_override", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_transactions_buchungsdatum", "transactions", ["buchungsdatum"])
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"])


def downgrade() -> None:
    op.drop_table("rules")
    op.drop_table("transactions")
    op.drop_table("accounts")
    op.drop_table("categories")