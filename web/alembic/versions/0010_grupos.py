"""Grupos: grupos, miembros e invitaciones

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('grupos',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('nombre', sa.String(length=60), nullable=False),
                    sa.Column('creado_por', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
                    sa.Column('creado', sa.DateTime(), nullable=False))
    op.create_table('miembros_grupo',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('grupo_id', sa.Integer(), sa.ForeignKey('grupos.id'), nullable=False),
                    sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
                    sa.Column('rol', sa.String(length=10), nullable=False, server_default='miembro'),
                    sa.Column('pausado', sa.Boolean(), nullable=False, server_default=sa.false()),
                    sa.Column('unido', sa.DateTime(), nullable=False),
                    sa.UniqueConstraint('grupo_id', 'usuario_id'))
    op.create_index('ix_miembros_grupo_grupo_id', 'miembros_grupo', ['grupo_id'])
    op.create_index('ix_miembros_grupo_usuario_id', 'miembros_grupo', ['usuario_id'])
    op.create_table('invitaciones_grupo',
                    sa.Column('token_hash', sa.String(length=64), primary_key=True),
                    sa.Column('grupo_id', sa.Integer(), sa.ForeignKey('grupos.id'), nullable=False),
                    sa.Column('creada_por', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
                    sa.Column('creada', sa.DateTime(), nullable=False),
                    sa.Column('expira', sa.DateTime(), nullable=False))
    op.create_index('ix_invitaciones_grupo_grupo_id', 'invitaciones_grupo', ['grupo_id'])


def downgrade() -> None:
    op.drop_table('invitaciones_grupo')
    op.drop_table('miembros_grupo')
    op.drop_table('grupos')
