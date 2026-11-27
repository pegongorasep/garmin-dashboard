"""Actividades registradas a mano (E4)

Revision ID: 0020
Revises: 0019
"""
import sqlalchemy as sa
from alembic import op


revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('actividades_manuales',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
                    sa.Column('fecha', sa.Date(), nullable=False),
                    sa.Column('tipo', sa.String(length=30), nullable=False),
                    sa.Column('distancia_m', sa.Integer(), nullable=True),
                    sa.Column('duracion_s', sa.Integer(), nullable=False),
                    sa.Column('esfuerzo', sa.Integer(), nullable=True),
                    sa.Column('fc_prom', sa.Integer(), nullable=True),
                    sa.Column('nota', sa.String(length=280), nullable=True),
                    sa.Column('creada', sa.DateTime(), nullable=False),
                    sa.Column('actualizada', sa.DateTime(), nullable=False))
    op.create_index('ix_actividades_manuales_usuario_id', 'actividades_manuales', ['usuario_id'])


def downgrade() -> None:
    op.drop_index('ix_actividades_manuales_usuario_id', table_name='actividades_manuales')
    op.drop_table('actividades_manuales')
