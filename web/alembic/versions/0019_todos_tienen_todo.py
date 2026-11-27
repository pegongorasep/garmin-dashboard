"""Todos tienen todo: quien estaba en «solo cuerpo» pasa a uso NULL y sin plan (la columna uso se queda)

Revision ID: 0019
Revises: 0018
"""
from alembic import op


revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE usuarios SET uso = NULL, sin_plan = true WHERE uso = 'cuerpo'")


def downgrade() -> None:
    pass   # no se puede saber quién venía de «solo cuerpo»; quedan con todo y sin plan
