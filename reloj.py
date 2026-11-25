"""Entrenamientos del reloj (solo en la Mac de Pedro; no lo usa el workflow ni la plantilla).

Usa las APIs internas de Garmin Connect con la librería no oficial `garminconnect` (la Personal API solo lee).
La contraseña no se guarda: el login deja tokens de sesión en ~/.garminconnect (fuera del repo).

Uso:
  .venv/bin/python reloj.py login            # en la Terminal de la Mac (pide correo, contraseña y código MFA)
  .venv/bin/python reloj.py lista            # entrenamientos de la biblioteca
  .venv/bin/python reloj.py borrar ID [ID…]  # borra esos entrenamientos
  .venv/bin/python reloj.py semana           # muestra qué mandaría de la semana del plan (no escribe nada)
  .venv/bin/python reloj.py semana --si      # lo manda de verdad (borra lo viejo, sube y envía al reloj)
"""
import argparse
import getpass
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from garminconnect import Garmin

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ / "dashboard"))
import build  # noqa: E402
import reloj_plan as rp  # noqa: E402
from ajustes import USER_DIR, cargar_config  # noqa: E402

TOKENS = Path.home() / ".garminconnect"
ESTADO = USER_DIR / "data" / "reloj.json"   # IDs de Garmin de lo que mandó el plan; gitignored, nunca se publica
SIN_SESION = ("No hay sesión de Garmin (o caducó). En la Terminal de la Mac corre:\n"
              "  cd ~/Desktop/garmin && .venv/bin/python reloj.py login")


def cliente() -> Garmin:
    if not TOKENS.exists():
        sys.exit(SIN_SESION)
    g = Garmin()
    try:
        g.login(str(TOKENS))
    except Exception as e:   # tokens vencidos o Garmin cambió algo
        sys.exit(f"{SIN_SESION}\n(detalle: {type(e).__name__})")
    return g


def login() -> None:
    if not sys.stdin.isatty():
        sys.exit("El login necesita escribir la contraseña: córrelo en la Terminal de la Mac, no dentro de Claude.")
    correo = input("Correo de Garmin: ").strip()
    clave = getpass.getpass("Contraseña (no se muestra ni se guarda): ")
    g = Garmin(correo, clave, prompt_mfa=lambda: input("Código que te mandó Garmin: ").strip())
    g.login(str(TOKENS))
    TOKENS.chmod(0o700)
    print(f"Listo: sesión guardada en {TOKENS}. Ya puedes volver a Claude.")


def todos(g: Garmin) -> list:
    out, inicio = [], 0
    while True:
        lote = g.get_workouts(inicio, 100) or []
        out += lote
        if len(lote) < 100:
            return out
        inicio += 100


def lista(g: Garmin) -> list:
    ws = todos(g)
    if not ws:
        print("La biblioteca de entrenamientos está vacía.")
    for w in ws:
        deporte = (w.get("sportType") or {}).get("sportTypeKey", "?")
        fecha = (w.get("createdDate") or w.get("updatedDate") or "")[:10]
        print(f"{w['workoutId']}\t{fecha}\t{deporte}\t{w.get('workoutName', '')}")
    print(f"Total: {len(ws)}")
    return ws


def borrar(g: Garmin, ids: list) -> None:
    ok = 0
    for i in ids:
        try:
            g.delete_workout(i)
            ok += 1
        except Exception as e:
            print(f"No se pudo borrar {i}: {type(e).__name__}")
    print(f"Borrados: {ok} de {len(ids)}")


def leer_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text())
    except (OSError, ValueError):
        return {"semana": None, "enviados": [], "dispositivo": None}


def guardar_estado(est: dict) -> None:
    ESTADO.parent.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(est, ensure_ascii=False, indent=1))


def actualizar_datos() -> None:
    """Baja los datos de Garmin para saber qué sesiones están hechas; si falla, sigue con lo que haya."""
    r = subprocess.run([sys.executable, str(RAIZ / "garmin_connect.py")], capture_output=True, text=True)
    if r.returncode:
        print("Aviso: no se pudieron actualizar los datos (garmin_connect.py falló); uso los que ya hay.")


def lunes_de(est: dict, config: dict) -> date:
    """Lunes de la semana en que se mandaron los `enviados` (guardado; si falta, se deduce del número de semana)."""
    if est.get("lunes"):
        return date.fromisoformat(est["lunes"])
    return build.monday(date.fromisoformat(config["plan_start"])) + timedelta(weeks=(est["semana"] or 1) - 1)


def lista_semana(g, n: int, config: dict, plan: dict, conservados: list) -> list:
    """(sesión, entrenamiento) por subir de la semana `n`; sin repetir una sesión que ya está en `conservados`."""
    semana = next((w for w in plan["weeks"] if w["n"] == n), None)
    if semana is None:
        sys.exit(f"El plan no tiene semana {n}.")
    ya = {(e.get("semana_n"), e["sesion"]) for e in conservados}
    return [(s, rp.entrenamiento(s, n)) for s in semana["sessions"] if (n, s["id"]) not in ya]


def dispositivo(g: Garmin, guardado):
    """Reloj principal; si Garmin no tiene uno marcado, el último que sincronizó; si no, el guardado."""
    for buscar in (lambda: g.get_primary_training_device()["PrimaryTrainingDevice"]["deviceId"],
                   lambda: g.get_device_last_used()["userDeviceId"]):
        try:
            if (d := buscar()):
                return int(d)
        except Exception:
            pass
    return guardado


def semana(a) -> None:
    config = cargar_config()
    hoy = datetime.now(ZoneInfo(config["timezone"])).date()
    plan, data = build.load_plan(), None
    n = a.semana or rp.semana_actual(hoy, config, plan)
    if n is None:
        sys.exit("Hoy no hay semana de plan activa (usa --semana N para elegir una).")
    actualizar_datos()
    data = build.load_data()
    est = leer_estado()
    enviados = [{**e, "semana_n": e.get("semana_n", est.get("semana"))} for e in est.get("enviados", [])]
    pendientes, borrar_ya = [], []
    if enviados:
        dia = lunes_de(est, config)
        _, estado = build.week_assignment(dia, data, config, plan, hasta=dia + timedelta(days=6))
        borrar_ya, pendientes = rp.clasificar(enviados, estado)
    if a.si and pendientes and not (a.borrar_pendientes or a.conservar_pendientes):
        sys.exit("Hay pendientes de una semana anterior: elige --borrar-pendientes o --conservar-pendientes.")
    borrar = borrar_ya + (pendientes if a.borrar_pendientes else [])
    conservados = [] if a.borrar_pendientes else pendientes
    por_subir = lista_semana(None, n, config, plan, conservados)

    print(f"Semana {n} del plan ({'ESCRIBIENDO en Garmin' if a.si else 'simulación: no se escribe nada'})")
    print("\nSe borra de Garmin:" if borrar else "\nNo hay nada que borrar.")
    for e in borrar:
        print(f"  - {e['nombre']}")
    for e in pendientes:
        if not a.si or not (a.borrar_pendientes or a.conservar_pendientes):
            print(f"Pregunta: {e['nombre']} sigue pendiente, ¿la borro o la conservo?")
    for e in (conservados if a.si else []):
        print(f"  (se conserva {e['nombre']})")
    print("\nSe sube y se manda al reloj:")
    for s, w in por_subir:
        print(f"  + {w['workoutName']}: {rp.resumen_pasos(s['steps'])}")
    if not por_subir:
        print("  (nada: la semana ya está en el reloj)")
    if not a.si:
        print("\nSimulación terminada. Para mandarlo de verdad: agrega --si.")
        return

    g = cliente()
    restantes = list(conservados)
    for e in borrar:
        try:
            g.delete_workout(e["id"])
        except Exception as ex:
            if "404" in str(ex) or "not found" in str(ex).lower():
                continue   # ya no existe en Garmin: cuenta como borrado
            print(f"No se pudo borrar {e['nombre']}: {type(ex).__name__}")
            restantes.append(e)
    est = {**est, "semana": n, "lunes": build.monday(hoy).isoformat(), "enviados": restantes}
    est["dispositivo"] = dispositivo(g, est.get("dispositivo"))
    guardar_estado(est)
    for s, w in por_subir:
        try:
            r = g.upload_workout(w)
            wid = int(r["workoutId"])
            est["enviados"].append({"id": wid, "sesion": s["id"], "nombre": w["workoutName"], "semana_n": n})
            guardar_estado(est)   # después de cada subida: si se corta, no se pierden los IDs
            if est["dispositivo"]:
                g.push_workout_to_device(wid, est["dispositivo"])
        except Exception as ex:
            print(f"Garmin falló con {w['workoutName']}: {type(ex).__name__}. No reintento; revisa con `reloj.py lista`.")
            break
    print("\nEn tu reloj: Entrenamiento › Entrenamientos. Quedó:")
    for e in est["enviados"]:
        print(f"  {e['nombre']}")


def main() -> None:
    p = argparse.ArgumentParser(description="Entrenamientos del reloj")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    sub.add_parser("lista")
    b = sub.add_parser("borrar")
    b.add_argument("ids", nargs="*", type=int)
    s = sub.add_parser("semana")
    s.add_argument("--semana", type=int, help="semana del plan (por defecto la de hoy)")
    s.add_argument("--si", action="store_true", help="escribir de verdad en Garmin")
    s.add_argument("--borrar-pendientes", action="store_true")
    s.add_argument("--conservar-pendientes", action="store_true")
    a = p.parse_args()
    if a.cmd == "semana":
        return semana(a)
    if a.cmd == "login":
        return login()
    if a.cmd == "borrar" and not a.ids:
        sys.exit("Dime qué borrar: uno o más IDs (ver `lista`)")
    g = cliente()
    if a.cmd == "lista":
        lista(g)
    else:
        borrar(g, a.ids)


if __name__ == "__main__":
    main()
