"""Perfil: nombre, apellido y foto

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('usuarios', sa.Column('nombre', sa.String(length=60), nullable=True))
    op.add_column('usuarios', sa.Column('apellido', sa.String(length=60), nullable=True))
    op.create_table('fotos_perfil',
                    sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), primary_key=True),
                    sa.Column('contenido', sa.LargeBinary(), nullable=False),
                    sa.Column('tipo', sa.String(length=20), nullable=False),
                    sa.Column('actualizada', sa.DateTime(), nullable=False))


def downgrade() -> None:
    op.drop_table('fotos_perfil')
    op.drop_column('usuarios', 'apellido')
    op.drop_column('usuarios', 'nombre')
