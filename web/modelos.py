"""Tablas. Fechas en UTC sin zona (naive); JSON como sa.JSON para que SQLite (pruebas) y Postgres (producción) valgan."""
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def ahora() -> datetime:
    """Ahora en UTC, sin zona (así se guarda todo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    correo: Mapped[str] = mapped_column(sa.String(320), unique=True)
    apodo: Mapped[str | None] = mapped_column(sa.String(80))
    es_admin: Mapped[bool] = mapped_column(default=False)
    creado: Mapped[datetime] = mapped_column(default=ahora)
    github_owner: Mapped[str | None] = mapped_column(sa.String(100))
    github_owner_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    repo: Mapped[str | None] = mapped_column(sa.String(200))          # "owner/nombre"
    repo_id: Mapped[int | None] = mapped_column(sa.BigInteger, index=True)
    google_sub: Mapped[str | None] = mapped_column(sa.String(64), unique=True)   # login con Google
    sensor: Mapped[str] = mapped_column(sa.String(10), default="banda")   # banda | muñeca
    historial_desde: Mapped[str | None] = mapped_column(sa.String(10))    # pedido pendiente: la siguiente corrida lo baja
    idioma: Mapped[str | None] = mapped_column(sa.String(5))              # es | en; None = el del navegador
    uso: Mapped[str | None] = mapped_column(sa.String(10))                # None = completo | cuerpo (solo mediciones)
    sin_plan: Mapped[bool] = mapped_column(default=False, server_default=sa.false())   # L1: sin plan de running (solo ver cómo va). Se fija en «¿Quieres un plan?» del onboarding (por defecto No = True); lo demás, con plan
    migrado: Mapped[bool] = mapped_column(default=False)                  # F8: Pages apagado
    nombre: Mapped[str | None] = mapped_column(sa.String(60))             # G1: None = aún no lo ha dicho (se le pide en /perfil)
    apellido: Mapped[str | None] = mapped_column(sa.String(60))
    compartir_actividades: Mapped[bool] = mapped_column(default=True, server_default=sa.true())   # Social: los grupos ven mis actividades (apagado: solo totales de la semana)
    compartir_plan: Mapped[bool] = mapped_column(default=True, server_default=sa.true())          # Social: los grupos ven mi plan (calendario, etapa, avance)
    juntos_visto: Mapped[datetime | None] = mapped_column()           # Social S4: la última vez que abrió Juntos (para el punto de «nuevo»); None = nunca
    gh_instalacion: Mapped[int | None] = mapped_column(sa.BigInteger)   # Conexión: id de la instalación de la GitHub App; None = no conectado así
    historial_pendiente: Mapped[bool] = mapped_column(default=False, server_default=sa.false())   # Conexión: la comprobación salió bien y falta bajar el historial
    borrado: Mapped[datetime | None] = mapped_column()


class FotoPerfil(Base):
    """G1: foto ya recodificada (256x256, sin EXIF). En la base porque Cloud Run no tiene disco."""
    __tablename__ = "fotos_perfil"
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), primary_key=True)
    contenido: Mapped[bytes] = mapped_column(sa.LargeBinary)
    tipo: Mapped[str] = mapped_column(sa.String(20), default="image/webp")
    actualizada: Mapped[datetime] = mapped_column(default=ahora)


class Grupo(Base):
    """G2: grupo de amigos. Quien lo crea es el rol "admin" (rol en MiembroGrupo)."""
    __tablename__ = "grupos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(sa.String(60))
    creado_por: Mapped[int | None] = mapped_column(sa.ForeignKey("usuarios.id"))
    creado: Mapped[datetime] = mapped_column(default=ahora)


class MiembroGrupo(Base):
    __tablename__ = "miembros_grupo"
    __table_args__ = (sa.UniqueConstraint("grupo_id", "usuario_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_id: Mapped[int] = mapped_column(sa.ForeignKey("grupos.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    rol: Mapped[str] = mapped_column(sa.String(10), default="miembro")   # admin | miembro
    pausado: Mapped[bool] = mapped_column(default=False)                  # «Pausar lo que comparto» (G3 lo respeta)
    unido: Mapped[datetime] = mapped_column(default=ahora)


class AvisoOculto(Base):
    """Un aviso del sitio que la persona dio por «Entendido». `huella` = lo que decía: si cambia, el aviso vuelve a salir."""
    __tablename__ = "avisos_ocultos"
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), primary_key=True)
    aviso_id: Mapped[str] = mapped_column(sa.String(20), primary_key=True)
    huella: Mapped[str] = mapped_column(sa.String(16))
    creado: Mapped[datetime] = mapped_column(default=ahora)


class ReaccionActividad(Base):
    """Social S3: emoji de una persona (`de_id`) a una actividad de otra (`dueno_id`). `clave` es opaca (HMAC con la SECRET_KEY),
    nunca un ID de Garmin. Si la actividad cambia (sesión encadenada que crece), su clave cambia y las reacciones no la siguen."""
    __tablename__ = "reacciones_actividad"
    __table_args__ = (sa.UniqueConstraint("clave", "dueno_id", "de_id", "emoji"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    clave: Mapped[str] = mapped_column(sa.String(32), index=True)
    dueno_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    de_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    emoji: Mapped[str] = mapped_column(sa.String(8))
    creada: Mapped[datetime] = mapped_column(default=ahora)


class Sincronizacion(Base):
    """Conexión: una corrida del workflow de la persona. tipo: comprobacion|historial|normal|treinta|programada;
    estado: esperando|corriendo|ok|error; error: sin_key|nombre_mal|key_rechazada|otra;
    paso: arranca|prepara|busca|encuentra|detalles|salud|sube|termina."""
    __tablename__ = "sincronizaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    tipo: Mapped[str] = mapped_column(sa.String(16))
    estado: Mapped[str] = mapped_column(sa.String(12), default="esperando")
    error: Mapped[str | None] = mapped_column(sa.String(32))
    paso: Mapped[str | None] = mapped_column(sa.String(16))
    hechos: Mapped[int | None] = mapped_column()
    total: Mapped[int | None] = mapped_column()
    nuevas: Mapped[int | None] = mapped_column()
    run_id: Mapped[int | None] = mapped_column(sa.BigInteger, index=True)
    creada: Mapped[datetime] = mapped_column(default=ahora)
    actualizada: Mapped[datetime] = mapped_column(default=ahora)
    terminada: Mapped[datetime | None] = mapped_column()


class Comentario(Base):
    """Social S4: comentario de una persona (`autor_id`) en una actividad de otra (`dueno_id`), colgado de la misma clave opaca que
    las reacciones. Texto plano, ≤ 280 caracteres."""
    __tablename__ = "comentarios_actividad"
    id: Mapped[int] = mapped_column(primary_key=True)
    clave: Mapped[str] = mapped_column(sa.String(32), index=True)
    dueno_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    autor_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    texto: Mapped[str] = mapped_column(sa.String(280))
    creado: Mapped[datetime] = mapped_column(default=ahora)


class InvitacionGrupo(Base):
    """Liga para unirse a un grupo; solo se guarda el hash. Vale varias veces hasta que expira."""
    __tablename__ = "invitaciones_grupo"
    token_hash: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    grupo_id: Mapped[int] = mapped_column(sa.ForeignKey("grupos.id"), index=True)
    creada_por: Mapped[int | None] = mapped_column(sa.ForeignKey("usuarios.id"))
    creada: Mapped[datetime] = mapped_column(default=ahora)
    expira: Mapped[datetime] = mapped_column()


class Invitacion(Base):
    __tablename__ = "invitaciones"
    token_hash: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    creada_por: Mapped[int | None] = mapped_column(sa.ForeignKey("usuarios.id"))
    nota: Mapped[str | None] = mapped_column(sa.String(200))
    creada: Mapped[datetime] = mapped_column(default=ahora)
    expira: Mapped[datetime] = mapped_column()
    usada_por: Mapped[int | None] = mapped_column(sa.ForeignKey("usuarios.id"))
    usada_en: Mapped[datetime | None] = mapped_column()


class LigaLogin(Base):
    __tablename__ = "ligas_login"
    token_hash: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    creada: Mapped[datetime] = mapped_column(default=ahora)
    expira: Mapped[datetime] = mapped_column()
    usada_en: Mapped[datetime | None] = mapped_column()


class CodigoLogin(Base):
    __tablename__ = "codigos_login"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    codigo_hash: Mapped[str] = mapped_column(sa.String(64))   # HMAC del código con la SECRET_KEY; el código no se guarda
    creada: Mapped[datetime] = mapped_column(default=ahora)
    expira: Mapped[datetime] = mapped_column()
    intentos: Mapped[int] = mapped_column(default=0)
    usada_en: Mapped[datetime | None] = mapped_column()


class Sesion(Base):
    __tablename__ = "sesiones"
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)   # sha256 del valor de la cookie
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    creada: Mapped[datetime] = mapped_column(default=ahora)
    expira: Mapped[datetime] = mapped_column()
    ultima_vez: Mapped[datetime] = mapped_column(default=ahora)


class Consentimiento(Base):
    __tablename__ = "consentimientos"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    version_aviso: Mapped[str] = mapped_column(sa.String(20))
    fecha: Mapped[datetime] = mapped_column(default=ahora)


class DatoGarmin(Base):
    __tablename__ = "datos_garmin"
    __table_args__ = (sa.UniqueConstraint("usuario_id", "tipo", "clave"),)
    id: Mapped[int] = mapped_column(primary_key=True)   # el orden de inserción es el orden de lectura
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    tipo: Mapped[str] = mapped_column(sa.String(20))    # actividad detalle dia sueno hrv zonas historial meta
    clave: Mapped[str] = mapped_column(sa.String(64))
    contenido: Mapped[dict | list] = mapped_column(sa.JSON)
    actualizado: Mapped[datetime] = mapped_column(default=ahora)


class Subida(Base):
    __tablename__ = "subidas"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    fecha: Mapped[datetime] = mapped_column(default=ahora)
    motor: Mapped[str | None] = mapped_column(sa.String(64))
    bytes: Mapped[int] = mapped_column(default=0)
    ok: Mapped[bool] = mapped_column(default=True)
    error: Mapped[str | None] = mapped_column(sa.Text)


class Ajustes(Base):
    __tablename__ = "ajustes"
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), primary_key=True)
    config: Mapped[dict] = mapped_column(sa.JSON)   # mismo formato que config.yaml
    version: Mapped[int] = mapped_column(default=1)
    actualizado: Mapped[datetime] = mapped_column(default=ahora)


class Plan(Base):
    __tablename__ = "planes"
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), primary_key=True)
    plan: Mapped[dict] = mapped_column(sa.JSON)     # formato de plan.json
    version: Mapped[int] = mapped_column(default=1)
    actualizado: Mapped[datetime] = mapped_column(default=ahora)


class InBody(Base):
    __tablename__ = "inbody"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    fecha: Mapped[str] = mapped_column(sa.String(10))
    valores: Mapped[dict] = mapped_column(sa.JSON)  # una entrada de plan/inbody.json
    actualizado: Mapped[datetime] = mapped_column(default=ahora)


class Cambio(Base):
    __tablename__ = "cambios"
    id: Mapped[int] = mapped_column(primary_key=True)
    atleta_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    autor_id: Mapped[int | None] = mapped_column(sa.ForeignKey("usuarios.id"))
    via: Mapped[str] = mapped_column(sa.String(10))   # web ia coach sistema
    descripcion: Mapped[str] = mapped_column(sa.Text)
    antes: Mapped[dict | list | None] = mapped_column(sa.JSON)
    despues: Mapped[dict | list | None] = mapped_column(sa.JSON)
    fecha: Mapped[datetime] = mapped_column(default=ahora)
    visto: Mapped[bool] = mapped_column(default=False)
    deshecho_por: Mapped[int | None] = mapped_column()


class Coach(Base):
    __tablename__ = "coaches"
    __table_args__ = (sa.UniqueConstraint("atleta_id", "coach_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    atleta_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    coach_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    creado: Mapped[datetime] = mapped_column(default=ahora)


class CacheData(Base):
    __tablename__ = "cache_data"
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), primary_key=True)
    contenido: Mapped[dict] = mapped_column(sa.JSON)
    calculado: Mapped[datetime] = mapped_column(default=ahora)
    huella: Mapped[str] = mapped_column(sa.String(64))


class VinculoPendiente(Base):
    """Repo privado que dice ser de un usuario y aún no lo probó: se vincula al escribir el código de 6 dígitos que
    solo se ve en el resumen de la corrida de ese repo. El código no se guarda: solo su hash (y un nonce para poder
    mostrarlo de nuevo mientras vive el pendiente)."""
    __tablename__ = "vinculos_pendientes"
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), primary_key=True)
    repo: Mapped[str] = mapped_column(sa.String(200))
    repo_id: Mapped[int] = mapped_column(sa.BigInteger)
    owner_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    nonce: Mapped[str] = mapped_column(sa.String(64))
    codigo_hash: Mapped[str] = mapped_column(sa.String(64))
    creado: Mapped[datetime] = mapped_column(default=ahora)
    expira: Mapped[datetime] = mapped_column()
    intentos: Mapped[int] = mapped_column(default=0)


class ClienteOAuth(Base):
    """F6a: cliente registrado de forma dinámica (RFC 7591), público (sin secreto)."""
    __tablename__ = "oauth_clientes"
    client_id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    nombre: Mapped[str] = mapped_column(sa.String(100))
    redirect_uris: Mapped[list] = mapped_column(sa.JSON)
    creado: Mapped[datetime] = mapped_column(default=ahora)


class CodigoOAuth(Base):
    """Código de autorización: solo su hash, de un solo uso, vence en 10 minutos."""
    __tablename__ = "oauth_codigos"
    codigo_hash: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(sa.ForeignKey("oauth_clientes.client_id"))
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    redirect_uri: Mapped[str] = mapped_column(sa.String(500))
    code_challenge: Mapped[str] = mapped_column(sa.String(128))
    resource: Mapped[str | None] = mapped_column(sa.String(500))
    expira: Mapped[datetime] = mapped_column()
    usado_en: Mapped[datetime | None] = mapped_column()


class TokenOAuth(Base):
    """Un par acceso/refresh por conexión. Solo hashes; el refresh rota en cada uso (se reescribe la misma fila)."""
    __tablename__ = "oauth_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(sa.ForeignKey("oauth_clientes.client_id"))
    usuario_id: Mapped[int] = mapped_column(sa.ForeignKey("usuarios.id"), index=True)
    acceso_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    refresh_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    resource: Mapped[str | None] = mapped_column(sa.String(500))
    creado: Mapped[datetime] = mapped_column(default=ahora)
    expira_acceso: Mapped[datetime] = mapped_column()
    expira_refresh: Mapped[datetime] = mapped_column()
    ultimo_uso: Mapped[datetime | None] = mapped_column()


class CuentaBorrada(Base):
    """F7a: registro anónimo de una cuenta borrada: solo la fecha, ningún dato de la persona."""
    __tablename__ = "cuentas_borradas"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[datetime] = mapped_column(default=ahora)
