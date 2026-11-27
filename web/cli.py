"""Comandos de admin: `python -m web.cli invitar|crear-admin|importar`. En producción corren como Cloud Run Job."""
import argparse
import sys

from sqlalchemy import select

from . import auth, importar, tubo
from .config import desde_entorno
from .db import crear_motor, crear_sesiones
from .modelos import Usuario


def main(argv=None, settings=None, motor=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m web.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("invitar", help="crea una invitación de un solo uso (14 días) e imprime la liga")
    p.add_argument("--nota", default=None, help="para quién es (p. ej. Adrián)")
    p = sub.add_parser("crear-admin", help="crea (o marca) al administrador")
    p.add_argument("correo")
    p.add_argument("--github-owner", default=None)
    p = sub.add_parser("importar", help="carga config.yaml, plan, InBody y data/ de una carpeta a una cuenta")
    p.add_argument("correo")
    p.add_argument("carpeta")
    p.add_argument("--repo-id", default="importar", help="id numérico del repo de GitHub (la sal de los ids de actividad)")
    p = sub.add_parser("vincular", help="liga a mano la cuenta con su repo (repos públicos, como el de Pedro)")
    p.add_argument("correo")
    p.add_argument("repo", help="owner/nombre")
    p.add_argument("repo_id", type=int, help="id numérico del repo (GITHUB_REPOSITORY_ID)")
    p = sub.add_parser("convertir-v6", help="convierte los planes que no son v6 al motor v6 (sin --aplicar solo ensaya e imprime)")
    p.add_argument("--aplicar", action="store_true", help="escribe los cambios (con historial, se pueden deshacer)")
    p.add_argument("--correo", default=None, help="solo esa cuenta")
    args = ap.parse_args(argv)

    settings = settings or desde_entorno()
    motor = motor or crear_motor(settings.database_url)
    db = crear_sesiones(motor)()
    try:
        if args.cmd == "invitar":
            admin = db.scalar(select(Usuario).where(Usuario.es_admin.is_(True)))
            token = auth.crear_invitacion(db, admin.id if admin else None, args.nota)
            print(f"{settings.base_url}/invitacion/{token}")
            print("(una sola vez, vence en 14 días)", file=sys.stderr)
        elif args.cmd == "crear-admin":
            u = auth.crear_admin(db, args.correo)
            if args.github_owner:
                u.github_owner = args.github_owner
                db.commit()
            print(f"Admin listo: {u.correo}")
        elif args.cmd == "convertir-v6":
            from datetime import datetime, timezone

            from . import convertir_v6
            return 1 if convertir_v6.correr(db, datetime.now(timezone.utc), args.aplicar, args.correo) else 0
        elif args.cmd == "vincular":
            u = auth.buscar_por_correo(db, args.correo)
            if u is None or args.repo.count("/") != 1:
                print("Cuenta o repo no válidos (usa owner/nombre)", file=sys.stderr)
                return 1
            tubo.vincular(db, u, args.repo, args.repo_id, None, f"Repo vinculado a mano: {args.repo}")
            u.github_owner = u.github_owner or args.repo.split("/")[0]
            db.commit()
            print(f"Vinculado: {u.correo} -> {args.repo} ({args.repo_id})")
        else:
            u = auth.buscar_por_correo(db, args.correo)
            if u is None:
                print(f"No hay cuenta con {args.correo}", file=sys.stderr)
                return 1
            print(importar.importar_carpeta(db, u, args.carpeta, salt=args.repo_id))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
