"""Login por código de 6 dígitos: tabla codigos_login

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'codigos_login',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('codigo_hash', sa.String(length=64), nullable=False),
        sa.Column('creada', sa.DateTime(), nullable=False),
        sa.Column('expira', sa.DateTime(), nullable=False),
        sa.Column('intentos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('usada_en', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_codigos_login_usuario_id', 'codigos_login', ['usuario_id'])


def downgrade() -> None:
    op.drop_index('ix_codigos_login_usuario_id', table_name='codigos_login')
    op.drop_table('codigos_login')
