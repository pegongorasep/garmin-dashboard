"""Conexión C2: sincronizaciones, gh_instalacion e historial_pendiente

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa


revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('usuarios', sa.Column('gh_instalacion', sa.BigInteger(), nullable=True))
    op.add_column('usuarios', sa.Column('historial_pendiente', sa.Boolean(), nullable=False,
                                        server_default=sa.false()))
    op.create_table('sincronizaciones',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
                    sa.Column('tipo', sa.String(length=16), nullable=False),
                    sa.Column('estado', sa.String(length=12), nullable=False),
                    sa.Column('error', sa.String(length=32), nullable=True),
                    sa.Column('paso', sa.String(length=16), nullable=True),
                    sa.Column('hechos', sa.Integer(), nullable=True),
                    sa.Column('total', sa.Integer(), nullable=True),
                    sa.Column('nuevas', sa.Integer(), nullable=True),
                    sa.Column('run_id', sa.BigInteger(), nullable=True),
                    sa.Column('creada', sa.DateTime(), nullable=False),
                    sa.Column('actualizada', sa.DateTime(), nullable=False),
                    sa.Column('terminada', sa.DateTime(), nullable=True))
    op.create_index('ix_sincronizaciones_usuario_id', 'sincronizaciones', ['usuario_id'])
    op.create_index('ix_sincronizaciones_run_id', 'sincronizaciones', ['run_id'])


def downgrade() -> None:
    op.drop_table('sincronizaciones')
    op.drop_column('usuarios', 'historial_pendiente')
    op.drop_column('usuarios', 'gh_instalacion')
