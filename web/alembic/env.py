"""Alembic: la URL sale de DATABASE_URL (o de `-x url=...`); nunca está en el repo."""
from alembic import context
from sqlalchemy import pool

from web.config import desde_entorno
from web.db import crear_motor
from web.modelos import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return context.get_x_argument(as_dictionary=True).get("url") or desde_entorno().database_url


def run_migrations_online() -> None:
    motor = config.attributes.get("connection") or crear_motor(_url())
    if hasattr(motor, "connect") and not hasattr(motor, "execute"):
        with motor.connect() as conexion:
            context.configure(connection=conexion, target_metadata=target_metadata, render_as_batch=True)
            with context.begin_transaction():
                context.run_migrations()
    else:
        context.configure(connection=motor, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
