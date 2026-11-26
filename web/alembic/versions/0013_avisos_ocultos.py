"""Avisos que la persona dio por «Entendido» (con la huella de lo que decían)

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('avisos_ocultos',
                    sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), primary_key=True),
                    sa.Column('aviso_id', sa.String(20), primary_key=True),
                    sa.Column('huella', sa.String(16), nullable=False),
                    sa.Column('creado', sa.DateTime(), nullable=False))


def downgrade() -> None:
    op.drop_table('avisos_ocultos')
