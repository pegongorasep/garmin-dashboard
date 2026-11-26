"""Login con Google: columna google_sub

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('usuarios') as b:
        b.add_column(sa.Column('google_sub', sa.String(length=64), nullable=True))
        b.create_unique_constraint('uq_usuarios_google_sub', ['google_sub'])


def downgrade() -> None:
    with op.batch_alter_table('usuarios') as b:
        b.drop_constraint('uq_usuarios_google_sub', type_='unique')
        b.drop_column('google_sub')
