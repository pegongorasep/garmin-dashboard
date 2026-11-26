"""Modalidad de la cuenta (nulo = completo | cuerpo)

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('usuarios', sa.Column('uso', sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column('usuarios', 'uso')
