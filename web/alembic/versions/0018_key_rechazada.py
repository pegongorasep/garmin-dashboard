"""Conexión C11: key_rechazada_desde

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa


revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('usuarios', sa.Column('key_rechazada_desde', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('usuarios', 'key_rechazada_desde')
