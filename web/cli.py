"""Comandos de admin: `python -m web.cli invitar|crear-admin|importar`. En producción corren como Cloud Run Job."""
import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select

from . import ROOT, auth, cambios, importar, tubo
from .config import desde_entorno
from .db import crear_motor, crear_sesiones
from .modelos import Ajustes, CacheData, Cambio, Usuario


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
    p = sub.add_parser("deshacer-cambio", help="deshace un cambio del historial (p. ej. el que dejó cargar-plan-viejo)")
    p.add_argument("cambio_id", type=int)
    p = sub.add_parser("cargar-plan-viejo", help="reemplaza el plan de la cuenta por el plan viejo (plan.json) convertido al formato v6")
    p.add_argument("correo")
    p.add_argument("--archivo", default=None, help="por defecto plan/plan.json (o plan/plan_viejo.json en la imagen)")
    p.add_argument("--nivel", default="base", help="nivel v6 de la conversión (supuesto: base)")
    p.add_argument("--carrera", default="2027-01-10", help="fecha de la carrera de 10 km (meta con fecha; no cambia las sesiones)")
    p.add_argument("--km", type=int, default=10)
    p.add_argument("--si", action="store_true", help="sin esto solo imprime el resumen y no escribe nada")
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
        elif args.cmd == "vincular":
            u = auth.buscar_por_correo(db, args.correo)
            if u is None or args.repo.count("/") != 1:
                print("Cuenta o repo no válidos (usa owner/nombre)", file=sys.stderr)
                return 1
            tubo.vincular(db, u, args.repo, args.repo_id, None, f"Repo vinculado a mano: {args.repo}")
            u.github_owner = u.github_owner or args.repo.split("/")[0]
            db.commit()
            print(f"Vinculado: {u.correo} -> {args.repo} ({args.repo_id})")
        elif args.cmd == "deshacer-cambio":
            c = db.get(Cambio, args.cambio_id)
            if c is None:
                print("No existe ese cambio", file=sys.stderr)
                return 1
            cambios.deshacer(db, db.get(Usuario, c.atleta_id), c.id, via="sistema")
            db.query(CacheData).filter(CacheData.usuario_id == c.atleta_id).delete()
            db.commit()
            print(f"Cambio #{c.id} deshecho")
        elif args.cmd == "cargar-plan-viejo":
            return _cargar_plan_viejo(db, args)
        else:
            u = auth.buscar_por_correo(db, args.correo)
            if u is None:
                print(f"No hay cuenta con {args.correo}", file=sys.stderr)
                return 1
            print(importar.importar_carpeta(db, u, args.carpeta, salt=args.repo_id))
        return 0
    finally:
        db.close()


def _cargar_plan_viejo(db, args) -> int:
    import convertir_viejo as cv   # web/__init__ puso plan/ en sys.path
    u = auth.buscar_por_correo(db, args.correo)
    if u is None:
        print(f"No hay cuenta con {args.correo}", file=sys.stderr)
        return 1
    ruta = Path(args.archivo) if args.archivo else next((p for p in (ROOT / "plan" / "plan.json", ROOT / "plan" / "plan_viejo.json") if p.exists()), None)
    if ruta is None or not ruta.exists():
        print("No encuentro el plan viejo (usa --archivo)", file=sys.stderr)
        return 1
    try:
        plan = cv.convertir(json.loads(ruta.read_text()), nivel=args.nivel)
    except (ValueError, KeyError) as ex:
        print(f"No se pudo convertir: {ex}", file=sys.stderr)
        return 1
    print("\n".join(cv.resumen(plan)))
    print(f"Evento: carrera de {args.km} km el {args.carrera} (meta con fecha; las sesiones no cambian)")
    if not args.si:
        print("Prueba en seco: no se escribió nada. Agrega --si para reemplazar el plan.")
        return 0
    fila = db.get(Ajustes, u.id)
    if fila is None:
        print("La cuenta no tiene ajustes de entreno; no hay dónde poner la carrera", file=sys.stderr)
        return 1
    ajustes = cv.ajustes_con_carrera(fila.config, plan, args.carrera, args.km)
    desc = f"Plan viejo cargado en formato v6: {len(plan['weeks'])} semanas desde {plan['start']}, carrera de {args.km} km el {args.carrera}"
    c = cambios.aplicar_cambio(db, u, None, "sistema", desc, {"ajustes": ajustes, "plan": plan})   # el plan de hoy queda en `antes`
    db.query(CacheData).filter(CacheData.usuario_id == u.id).delete()
    db.commit()
    print(f"Listo (cambio #{c.id}). El plan anterior quedó guardado en ese cambio.")
    print(f"Para deshacer: en la web, Cambios, «Deshacer» el cambio #{c.id}; o con el Job: "
          f"gcloud run jobs execute ahi-cli --args=\"-m,web.cli,deshacer-cambio,{c.id}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
