"""Social S4: comentarios por actividad y «juntos_visto» (punto de nuevo)

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa


revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('comentarios_actividad',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('clave', sa.String(length=32), nullable=False),
                    sa.Column('dueno_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
                    sa.Column('autor_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
                    sa.Column('texto', sa.String(length=280), nullable=False),
                    sa.Column('creado', sa.DateTime(), nullable=False))
    op.create_index('ix_comentarios_actividad_clave', 'comentarios_actividad', ['clave'])
    op.create_index('ix_comentarios_actividad_dueno_id', 'comentarios_actividad', ['dueno_id'])
    op.create_index('ix_comentarios_actividad_autor_id', 'comentarios_actividad', ['autor_id'])
    op.add_column('usuarios', sa.Column('juntos_visto', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('usuarios', 'juntos_visto')
    op.drop_table('comentarios_actividad')
