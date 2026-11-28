"""Arranca la web en local (`./run_web.sh`): contra la base de producción o, con `--temporal`, contra web/dev.db.

La cadena de la base de producción vive solo en la memoria y el entorno de este proceso (y del que recarga uvicorn):
nunca se imprime, no se escribe a disco ni va en los argumentos de un comando. Por eso los errores de la base se
reportan solo con el nombre de su clase: el mensaje o el traceback podrían traerla.
En producción no se migra ni se cambia el esquema: si la revisión de la base no es la del código, no arranca.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE_TEMPORAL = ROOT / "web" / "dev.db"
SECRETO = "DATABASE_URL"
PREFIJOS_POSTGRES = ("postgres://", "postgresql://", "postgresql+psycopg://")
# Sin estas variables la web local no manda correos ni habla con GitHub o Google.
QUITAR = ("RESEND_API_KEY",)
QUITAR_PREFIJOS = ("GITHUB_APP_", "GOOGLE_")
VIGILAR = ("web", "dashboard", "plan", "i18n", "aprende")


class Aborta(Exception):
    """No se puede arrancar; el mensaje se muestra tal cual (nunca lleva la cadena de la base)."""


def _correr(comando: list[str], que: str) -> str:
    """Salida de `gh` o `gcloud`. Si falla se muestra solo su stderr: el stdout puede ser el secreto."""
    try:
        r = subprocess.run(comando, cwd=ROOT, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise Aborta(f"No se pudo {que}: no está instalado `{comando[0]}`.") from None
    except subprocess.TimeoutExpired:
        raise Aborta(f"No se pudo {que}: `{comando[0]}` no respondió en 60 s.") from None
    if r.returncode != 0:
        detalle = "\n".join(x for x in (r.stderr or "").splitlines() if "://" not in x).strip()
        raise Aborta(f"No se pudo {que} (`{comando[0]}` salió con {r.returncode}).\n{detalle}".rstrip())
    return r.stdout.strip()


def obtener_proyecto(env) -> str:
    proyecto = (env.get("GCP_PROYECTO") or "").strip()
    if not proyecto:
        proyecto = _correr(["gh", "variable", "get", "GCP_PROYECTO"],
                           "leer la variable GCP_PROYECTO (también puedes ponerla en el entorno)")
    if not proyecto:
        raise Aborta("GCP_PROYECTO está vacía: ponla en el entorno.")
    return proyecto


def obtener_cadena(proyecto: str) -> str:
    cadena = _correr(["gcloud", "secrets", "versions", "access", "latest", f"--secret={SECRETO}", "--project", proyecto],
                     f"leer el secreto {SECRETO} del proyecto {proyecto} (revisa `gcloud auth login`)")
    if not cadena.startswith(PREFIJOS_POSTGRES):   # vacía o rara: jamás se cae al SQLite por defecto
        raise Aborta(f"El secreto {SECRETO} está vacío o no es una cadena de Postgres. No se arranca.")
    return cadena


def revision_local() -> set[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "web" / "alembic"))
    return set(ScriptDirectory.from_config(cfg).get_heads())


def revision_en_base(cadena: str) -> set[str]:
    """Lo que dice `alembic_version`, en una transacción de solo lectura."""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool

        from web.config import Settings

        url = Settings(database_url=cadena, base_url="http://localhost").database_url   # postgres:// -> psycopg
        es_postgres = url.startswith("postgresql")
        motor = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 30} if es_postgres else {})
        try:
            with motor.connect() as conexion:
                if es_postgres:
                    conexion = conexion.execution_options(postgresql_readonly=True)
                return {fila[0] for fila in conexion.execute(text("SELECT version_num FROM alembic_version"))}
        finally:
            motor.dispose()
    except Exception as e:   # noqa: BLE001  ni mensaje ni traceback: pueden traer la cadena
        raise Aborta(f"No se pudo leer la revisión de la base ({type(e).__name__}). No se arranca.") from None


def cadena_de_produccion(env) -> tuple[str, str]:
    """(proyecto, cadena), ya con la revisión comprobada."""
    proyecto = obtener_proyecto(env)
    cadena = obtener_cadena(proyecto)
    en_base, local = revision_en_base(cadena), revision_local()
    if en_base != local:
        nombres = lambda r: ", ".join(sorted(r)) or "ninguna"   # noqa: E731
        raise Aborta(f"La base de producción está en la revisión {nombres(en_base)} y tu código en {nombres(local)}.\n"
                     "No se arranca: este modo nunca migra. Actualiza tu código (o despliega la web) para que "
                     "coincidan, o prueba con `./run_web.sh --temporal`.")
    return proyecto, cadena


def puerto_de(env) -> int:
    texto = (env.get("PORT") or "8000").strip()
    if not texto.isdigit() or not 0 < int(texto) < 65536:
        raise Aborta("PORT debe ser un número de puerto.")
    return int(texto)


def entorno_web(env, puerto: int, cadena: str) -> dict:
    """El entorno con el que corre la web local: sin correo, GitHub App ni Google, y con la base indicada."""
    limpio = {k: v for k, v in env.items() if k not in QUITAR and not k.startswith(QUITAR_PREFIJOS)}
    limpio["BASE_URL"] = f"http://localhost:{puerto}"
    limpio[SECRETO] = cadena   # siempre se pisa: un DATABASE_URL heredado no se usa
    limpio["AHI_SIN_CACHE"] = "1"   # calcula siempre y no toca la caché de data.json (ver web/calculo.py)
    return limpio


def migrar_temporal(env: dict) -> None:
    r = subprocess.run([sys.executable, "-m", "alembic", "-c", "web/alembic.ini", "upgrade", "head"], cwd=ROOT, env=env)
    if r.returncode != 0:
        raise Aborta("No se pudieron correr las migraciones de la base temporal (puedes borrar web/dev.db y repetir).")


def servir(puerto: int) -> None:
    import uvicorn

    os.chdir(ROOT)
    uvicorn.run("web.app:app", host="127.0.0.1", port=puerto, reload=True, app_dir=str(ROOT),
                reload_dirs=[str(ROOT / c) for c in VIGILAR if (ROOT / c).is_dir()])


def avisar(temporal: bool, proyecto: str, puerto: int) -> None:
    url = f"http://localhost:{puerto}"
    if temporal:
        cli = f"env -u DATABASE_URL BASE_URL={url} {sys.executable} -m web.cli"
        print(f"\nBase: TEMPORAL (SQLite en {BASE_TEMPORAL}); producción no se toca.\n"
              f"Para crear una invitación en esta base, en otra terminal:\n"
              f"  cd {ROOT} && {cli} invitar --nota prueba\n"
              f"(o una cuenta de admin: cambia `invitar --nota prueba` por `crear-admin tu@correo` y entra en {url}/entrar)")
    else:
        print(f"\nBase: PRODUCCIÓN (proyecto {proyecto}). OJO: lo que guardes aquí es real.")
    print(f"URL: {url}\n"
          "La liga de entrada (el código) sale en esta consola; no se manda ningún correo.\n"
          "Se recarga sola al cambiar un .py; los textos de i18n y aprende piden reiniciar.\n", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="./run_web.sh", description="Prueba la web en local.")
    ap.add_argument("--temporal", action="store_true", help="usa una base SQLite local (web/dev.db) en vez de producción")
    args = ap.parse_args(argv)
    try:
        puerto = puerto_de(os.environ)
        if args.temporal:
            proyecto, cadena = "", f"sqlite:///{BASE_TEMPORAL}"
        else:
            proyecto, cadena = cadena_de_produccion(os.environ)
        env = entorno_web(os.environ, puerto, cadena)
        if args.temporal:
            migrar_temporal(env)
        os.environ.clear()
        os.environ.update(env)
        avisar(args.temporal, proyecto, puerto)
        servir(puerto)
    except Aborta as e:
        print(e, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as e:   # noqa: BLE001  sin traceback: podría traer la cadena
        print(f"Error inesperado al arrancar ({type(e).__name__}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
