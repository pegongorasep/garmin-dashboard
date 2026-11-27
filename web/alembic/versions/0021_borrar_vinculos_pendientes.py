"""Conexión C12: retirar el vínculo por código.

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("vinculos_pendientes")


def downgrade() -> None:
    op.create_table("vinculos_pendientes",
                    sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), primary_key=True),
                    sa.Column("repo", sa.String(length=200), nullable=False),
                    sa.Column("repo_id", sa.BigInteger(), nullable=False),
                    sa.Column("owner_id", sa.BigInteger()),
                    sa.Column("nonce", sa.String(length=64), nullable=False),
                    sa.Column("codigo_hash", sa.String(length=64), nullable=False),
                    sa.Column("creado", sa.DateTime(), nullable=False),
                    sa.Column("expira", sa.DateTime(), nullable=False),
                    sa.Column("intentos", sa.Integer(), nullable=False))
