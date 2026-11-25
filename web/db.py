"""Motor y sesiones de SQLAlchemy. Neon se duerme: pool chico y pre-ping."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def crear_motor(url: str):
    if url.startswith("sqlite"):
        if ":memory:" in url or url in ("sqlite://", "sqlite:///"):
            return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_size=5, max_overflow=0, pool_pre_ping=True, pool_recycle=300)


def crear_sesiones(motor) -> sessionmaker:
    return sessionmaker(bind=motor, expire_on_commit=False)
