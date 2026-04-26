"""add hr_zone_deviation to run_logs

Revision ID: 6329811ea4bd
Revises: 003_encrypt_plaintext_tokens
Create Date: 2026-04-26 11:06:40.866420

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6329811ea4bd'
down_revision: Union[str, Sequence[str], None] = '003_encrypt_plaintext_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('run_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hr_zone_deviation', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('run_logs', schema=None) as batch_op:
        batch_op.drop_column('hr_zone_deviation')
