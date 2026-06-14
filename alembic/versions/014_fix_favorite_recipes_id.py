"""Fix favorite_recipes.id column type (INTEGER -> String UUID).

The favorite_recipes table was originally created with ``id INTEGER PRIMARY KEY``
on some installations, but the ORM model declares ``id`` as a String UUID
(``default=lambda: str(uuid.uuid4())``). Inserting a UUID string into the
INTEGER column fails with ``IntegrityError: datatype mismatch``, so every
"Add to Favorites" click returns a 500.

The table is empty in production, so we drop and recreate it with the
correct String id and JSON-style recipe_data columns.

Revision ID: 014_fix_favorite_recipes_id
Revises: 013_add_refresh_tokens
Create Date: 2026-05-20
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "014_fix_favorite_recipes_id"
down_revision: Union[str, Sequence[str], None] = "013_add_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("favorite_recipes")
    op.create_table(
        "favorite_recipes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipe_name", sa.String(), nullable=False),
        sa.Column("meal_type", sa.String(), nullable=False),
        sa.Column("recipe_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("favorite_recipes")
    op.create_table(
        "favorite_recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipe_name", sa.String(), nullable=False),
        sa.Column("meal_type", sa.String(), nullable=False),
        sa.Column("recipe_data", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
