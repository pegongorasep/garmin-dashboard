"""Entrenamientos del reloj (solo en la Mac de Pedro; no lo usa el workflow ni la plantilla).

Usa las APIs internas de Garmin Connect con la librería no oficial `garminconnect` (la Personal API solo lee).
La contraseña no se guarda: el login deja tokens de sesión en ~/.garminconnect (fuera del repo).

Uso:
  .venv/bin/python reloj.py login            # en la Terminal de la Mac (pide correo, contraseña y código MFA)
  .venv/bin/python reloj.py lista            # entrenamientos de la biblioteca
  .venv/bin/python reloj.py borrar ID [ID…]  # borra esos entrenamientos
"""
import argparse
import getpass
import sys
from pathlib import Path

from garminconnect import Garmin

TOKENS = Path.home() / ".garminconnect"
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


def main() -> None:
    p = argparse.ArgumentParser(description="Entrenamientos del reloj")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    sub.add_parser("lista")
    b = sub.add_parser("borrar")
    b.add_argument("ids", nargs="*", type=int)
    a = p.parse_args()
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
