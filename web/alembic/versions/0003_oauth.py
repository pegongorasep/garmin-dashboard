"""F6a: clientes, códigos y tokens de OAuth

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('oauth_clientes',
    sa.Column('client_id', sa.String(length=64), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('redirect_uris', sa.JSON(), nullable=False),
    sa.Column('creado', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('client_id')
    )
    op.create_table('oauth_codigos',
    sa.Column('codigo_hash', sa.String(length=64), nullable=False),
    sa.Column('client_id', sa.String(length=64), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('redirect_uri', sa.String(length=500), nullable=False),
    sa.Column('code_challenge', sa.String(length=128), nullable=False),
    sa.Column('resource', sa.String(length=500), nullable=True),
    sa.Column('expira', sa.DateTime(), nullable=False),
    sa.Column('usado_en', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['client_id'], ['oauth_clientes.client_id'], ),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('codigo_hash')
    )
    op.create_index(op.f('ix_oauth_codigos_usuario_id'), 'oauth_codigos', ['usuario_id'], unique=False)
    op.create_table('oauth_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.String(length=64), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('acceso_hash', sa.String(length=64), nullable=False),
    sa.Column('refresh_hash', sa.String(length=64), nullable=False),
    sa.Column('resource', sa.String(length=500), nullable=True),
    sa.Column('creado', sa.DateTime(), nullable=False),
    sa.Column('expira_acceso', sa.DateTime(), nullable=False),
    sa.Column('expira_refresh', sa.DateTime(), nullable=False),
    sa.Column('ultimo_uso', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['client_id'], ['oauth_clientes.client_id'], ),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('acceso_hash'),
    sa.UniqueConstraint('refresh_hash')
    )
    op.create_index(op.f('ix_oauth_tokens_usuario_id'), 'oauth_tokens', ['usuario_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_oauth_tokens_usuario_id'), table_name='oauth_tokens')
    op.drop_table('oauth_tokens')
    op.drop_index(op.f('ix_oauth_codigos_usuario_id'), table_name='oauth_codigos')
    op.drop_table('oauth_codigos')
    op.drop_table('oauth_clientes')
