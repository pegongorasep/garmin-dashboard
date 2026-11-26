"""Configuración por variables de entorno. Nada de secretos en el repo."""
import os
from dataclasses import dataclass, field
from pathlib import Path

WEB = Path(__file__).parent


def _local(url: str) -> bool:
    return url.startswith(("http://localhost", "http://127.0.0.1"))


@dataclass
class Settings:
    database_url: str = ""
    secret_key: str = ""
    base_url: str = "http://localhost:8000"
    resend_api_key: str = ""
    correo_de: str = "Ahí la Llevas <entrar@ahilallevas.com>"
    oidc_audience: str = ""
    admin_correo: str = ""
    # URL de las llaves públicas de GitHub Actions (se cambia solo en pruebas)
    jwks_url: str = "https://token.actions.githubusercontent.com/.well-known/jwks"
    plantilla_repo: str = "garmin-prueba"   # PLANTILLA_REPO; cambiar a PLANTILLA_V5_REPO cuando exista el repo definitivo
    nombre_repo_sugerido: str = "ahilallevas-datos"   # nombre que se propone para la copia de cada persona
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.database_url:
            self.database_url = f"sqlite:///{WEB / 'dev.db'}"
        if self.database_url.startswith("postgres://"):
            self.database_url = "postgresql+psycopg://" + self.database_url[len("postgres://"):]
        elif self.database_url.startswith("postgresql://"):
            self.database_url = "postgresql+psycopg://" + self.database_url[len("postgresql://"):]
        self.base_url = self.base_url.rstrip("/")
        if not self.secret_key:
            if not _local(self.base_url):
                raise RuntimeError("Falta SECRET_KEY (obligatoria fuera de localhost)")
            self.secret_key = "solo-para-desarrollo-local"
        self.oidc_audience = self.oidc_audience or self.base_url

    @property
    def cookie_segura(self) -> bool:
        """Cookies `Secure` siempre, salvo en localhost sobre http (desarrollo)."""
        return not _local(self.base_url)


# Plantilla definitiva de v5 (carpeta plantilla_v5/); aún no se crea en GitHub
PLANTILLA_V5_REPO = "ahi-la-llevas-plantilla"
PLANTILLA_V5_URL = f"https://github.com/pegongorasep/{PLANTILLA_V5_REPO}"


def desde_entorno() -> Settings:
    e = os.environ
    return Settings(database_url=e.get("DATABASE_URL", ""), secret_key=e.get("SECRET_KEY", ""),
                    base_url=e.get("BASE_URL", "http://localhost:8000"), resend_api_key=e.get("RESEND_API_KEY", ""),
                    correo_de=e.get("CORREO_DE", "Ahí la Llevas <entrar@ahilallevas.com>"),
                    oidc_audience=e.get("OIDC_AUDIENCE", ""), plantilla_repo=e.get("PLANTILLA_REPO", "garmin-prueba"), admin_correo=e.get("ADMIN_CORREO", ""))
