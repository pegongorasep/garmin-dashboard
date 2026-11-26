"""Grupos G4: reacciones

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('reacciones',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('grupo_id', sa.Integer(), sa.ForeignKey('grupos.id'), nullable=False),
                    sa.Column('de_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
                    sa.Column('para_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
                    sa.Column('semana', sa.String(length=10), nullable=False),
                    sa.Column('emoji', sa.String(length=8), nullable=False),
                    sa.Column('creada', sa.DateTime(), nullable=False),
                    sa.UniqueConstraint('grupo_id', 'de_id', 'para_id', 'semana', 'emoji'))
    op.create_index('ix_reacciones_grupo_id', 'reacciones', ['grupo_id'])
    op.create_index('ix_reacciones_de_id', 'reacciones', ['de_id'])
    op.create_index('ix_reacciones_para_id', 'reacciones', ['para_id'])


def downgrade() -> None:
    op.drop_table('reacciones')
