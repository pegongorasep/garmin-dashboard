"""Social S3: reacciones por actividad; se retira la tabla de reacciones de persona a persona

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa


revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('reacciones_actividad',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('clave', sa.String(length=32), nullable=False),
                    sa.Column('dueno_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
                    sa.Column('de_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
                    sa.Column('emoji', sa.String(length=8), nullable=False),
                    sa.Column('creada', sa.DateTime(), nullable=False),
                    sa.UniqueConstraint('clave', 'dueno_id', 'de_id', 'emoji'))
    op.create_index('ix_reacciones_actividad_clave', 'reacciones_actividad', ['clave'])
    op.create_index('ix_reacciones_actividad_dueno_id', 'reacciones_actividad', ['dueno_id'])
    op.create_index('ix_reacciones_actividad_de_id', 'reacciones_actividad', ['de_id'])
    op.drop_table('reacciones')   # las de persona a persona se descartan: ya no existen en la web


def downgrade() -> None:
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
    op.drop_table('reacciones_actividad')
