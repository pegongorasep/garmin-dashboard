"""Lo corre `motor.yml` en el repo de cada persona: pide instrucciones a la web y le sube el paquete de data/.

Solo `requests` y la librería estándar (más dashboard/paquete.py del motor). `instrucciones` nunca falla; `subir`
sale con 1 si la subida falla (se ve en rojo) y con 0 si subió o si el repo aún no está vinculado.

  python subir.py instrucciones   imprime los argumentos para garmin_connect.py (vacío = los de siempre)
  python subir.py avance <paso>   avisa a la web el paso de la corrida (nunca falla)
  python subir.py bajar <args>    corre garmin_connect.py avisando su avance; error -> aviso + salida 1
  python subir.py fallo           avisa `otra` si no se avisó ya un error (nunca falla)
  python subir.py subir           arma el paquete de <GARMIN_USER_DIR>/data y lo sube

Variables: AHILALLEVAS_URL (la web), ACTIONS_ID_TOKEN_REQUEST_URL/TOKEN (las pone GitHub con `id-token: write`),
GITHUB_REPOSITORY_ID (la sal de los ids), GARMIN_USER_DIR.
"""
import gzip
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # se corre como archivo: la raíz del repo al path

URL_POR_DEFECTO = "https://ahilallevas.com"
TIMEOUT = 60
REINTENTOS = 2
ESPERA = 5
SUBIDO, NO_VINCULADO, FALLO = "subido", "no_vinculado", "fallo"
ARGS_OK = re.compile(r"^(?:--dias-actividades [0-9]{1,4})?(?: ?--historial-desde [0-9]{4}-[0-9]{2}-[0-9]{2})?"
                     r"(?: ?--semanas-salud [0-9]{1,2})?$")
VERSION_MOTOR = 2
TIMEOUT_AVISO = 8
ESPACIO_AVISOS = 2.0   # segundos mínimos entre avisos de `detalles`


def _url() -> str:
    return os.environ.get("AHILALLEVAS_URL", URL_POR_DEFECTO).rstrip("/")


def _avisa(texto: str) -> None:
    print(f"[ahi-la-llevas] {texto}", file=sys.stderr)


def token_oidc(entorno=os.environ, http=requests) -> str:
    """Token OIDC de GitHub Actions con `audience` = la web."""
    url, token = entorno.get("ACTIONS_ID_TOKEN_REQUEST_URL"), entorno.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not token:
        raise RuntimeError("no hay token OIDC (¿falta `id-token: write`?)")
    r = http.get(url, params={"audience": _url()}, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["value"]


def _pedir(ruta: str, cuerpo: bytes | None, cabeceras: dict, http=requests, dormir=time.sleep):
    """POST con timeout de 60 s y 2 reintentos (Cloud Run puede estar despertando). Devuelve la respuesta o lanza."""
    ultimo = None
    for intento in range(REINTENTOS + 1):
        try:
            r = http.post(f"{_url()}{ruta}", data=cuerpo, headers=cabeceras, timeout=TIMEOUT)
            if r.status_code < 500:
                return r
            ultimo = RuntimeError(f"la web respondió {r.status_code}")
        except requests.RequestException as e:
            ultimo = e
        if intento < REINTENTOS:
            dormir(ESPERA)
    raise ultimo


def instrucciones(http=requests, dormir=time.sleep) -> str:
    """Argumentos para garmin_connect.py. Cualquier problema -> cadena vacía (los argumentos de hoy)."""
    try:
        r = _pedir("/api/tubo/instrucciones", json.dumps({"motor_version": VERSION_MOTOR}).encode(),
                   {"Authorization": f"Bearer {token_oidc(http=http)}", "Content-Type": "application/json",
                    "X-Motor-Version": str(VERSION_MOTOR)}, http, dormir)
        if r.status_code != 200:
            _avisa(f"la web no vinculó este repo (HTTP {r.status_code}); todo sigue como siempre")
            return ""
        d = r.json()
        args = []
        if d.get("dias_actividades"):
            args.append(f"--dias-actividades {int(d['dias_actividades'])}")
        if d.get("historial_desde"):
            args.append(f"--historial-desde {d['historial_desde']}")
        if d.get("semanas_salud"):
            args.append(f"--semanas-salud {int(d['semanas_salud'])}")
        texto = " ".join(args)
        return texto if ARGS_OK.match(texto) else ""   # nunca se pasa al shell algo con otra forma
    except Exception as e:   # noqa: BLE001  (nunca falla el workflow)
        _avisa(f"no se pudieron pedir instrucciones a la web ({type(e).__name__}); se usan las de siempre")
        return ""


def subir(data_dir: Path, entorno=os.environ, http=requests, dormir=time.sleep) -> str:
    """Sube el paquete. Devuelve SUBIDO, NO_VINCULADO (la persona aún no vincula su repo: no es un fallo) o FALLO."""
    try:
        from dashboard import paquete
        pq = paquete.armar(data_dir, salt=entorno.get("GITHUB_REPOSITORY_ID", ""))
        pers = paquete.personales(data_dir.parent)
        if pers:
            pq["personales"] = pers   # la web los importa solo la primera vez
        problemas = paquete.validar(pq)
        if problemas:
            _avisa("el paquete no pasó la lista blanca, no se sube: " + "; ".join(problemas))
            return FALLO
        cuerpo = gzip.compress(json.dumps(pq, separators=(",", ":")).encode())
        r = _pedir("/api/tubo/subida", cuerpo, {"Authorization": f"Bearer {token_oidc(entorno, http)}",
                                               "Content-Type": "application/json", "Content-Encoding": "gzip"}, http, dormir)
        if r.status_code == 200:
            print(f"[ahi-la-llevas] datos subidos ({len(cuerpo) / 1024:.0f} KB)")
            return SUBIDO
        if r.status_code == 403 and _error_de(r) == "repo no vinculado":
            _avisa("este repo aún no está vinculado a una cuenta de Ahí la Llevas: autoriza la GitHub App desde la web")
            return NO_VINCULADO
        _avisa(f"la web no aceptó el paquete (HTTP {r.status_code})")
    except Exception as e:   # noqa: BLE001
        _avisa(f"no se pudo subir a la web ({type(e).__name__}: {e})")
    return FALLO


def _marca() -> Path:
    base = os.environ.get("RUNNER_TEMP") or (Path(os.environ.get("GARMIN_USER_DIR") or ".") / "data")
    return Path(base) / "ahi-error-avisado"


def avisar(paso: str, hechos=None, total=None, error=None, entorno=os.environ, http=requests) -> bool:
    """Avisa el avance a la web. Nunca lanza; un 404 (web vieja) se ignora en silencio. True si la web lo recibió."""
    try:
        cuerpo = {"paso": paso}
        if hechos is not None:
            cuerpo["hechos"] = int(hechos)
        if total is not None:
            cuerpo["total"] = int(total)
        if error:
            cuerpo["error"] = error
        r = http.post(f"{_url()}/api/tubo/avance", data=json.dumps(cuerpo).encode(),
                      headers={"Authorization": f"Bearer {token_oidc(entorno, http)}", "Content-Type": "application/json"},
                      timeout=TIMEOUT_AVISO)
        return r.status_code == 200
    except Exception:   # noqa: BLE001
        return False


def avisar_error(codigo: str, entorno=os.environ, http=requests) -> None:
    avisar("termina", error=codigo, entorno=entorno, http=http)
    try:
        m = _marca()
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text(codigo)
    except Exception:   # noqa: BLE001
        pass


def bajar(args: list, main_garmin=None, entorno=os.environ, http=requests, reloj=time.monotonic) -> int:
    """Corre garmin_connect.main avisando el avance. Devuelve 0 o 1 (y avisa el error)."""
    if not entorno.get("PERSONAL_API_KEY"):
        _avisa("falta PERSONAL_API_KEY")
        avisar_error("sin_key", entorno, http)
        return 1
    ultimo = {}

    def avance(paso, hechos=None, total=None):
        t = reloj()
        if paso == "detalles" and t - ultimo.get(paso, -1e9) < ESPACIO_AVISOS and hechos != total:
            return
        ultimo[paso] = t
        avisar(paso, hechos, total, entorno=entorno, http=http)

    try:
        if main_garmin is None:
            import garmin_connect
            main_garmin = garmin_connect.main
        main_garmin(args, avance=avance)
        return 0
    except BaseException as e:   # noqa: BLE001  (SystemExit incluido: así se ve el mensaje de la key)
        if isinstance(e, SystemExit) and not e.code:
            return 0
        codigo = "key_rechazada" if (type(e).__name__ == "KeyRechazada" or _es_401(e)) else "otra"
        _avisa(str(e.code) if isinstance(e, SystemExit) and isinstance(e.code, str) else f"{type(e).__name__}: {e}")
        avisar_error(codigo, entorno, http)
        return 1


def _es_401(e) -> bool:
    r = getattr(e, "response", None)
    return getattr(r, "status_code", None) in (401, 403)


def fallo(entorno=os.environ, http=requests) -> None:
    """Paso `if: failure()`: avisa `otra` solo si no se avisó ya un error en esta corrida."""
    try:
        if not _marca().exists():
            avisar_error("otra", entorno, http)
    except Exception:   # noqa: BLE001
        pass


def _error_de(r) -> str:
    try:
        return str(r.json().get("error") or "")
    except Exception:   # noqa: BLE001
        return ""


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    orden = argv[0] if argv else ""
    if orden == "instrucciones":
        print(instrucciones())   # nunca falla: sin respuesta se usan los argumentos de siempre
    elif orden == "subir":
        # Un fallo real (web caída, paquete inválido, token) tumba el job para que se vea; "no vinculado" no.
        res = subir(Path(os.environ.get("GARMIN_USER_DIR") or ".") / "data")
        if res == SUBIDO:
            avisar("termina")
        return 1 if res == FALLO else 0
    elif orden == "avance":
        avisar(argv[1] if len(argv) > 1 else "arranca")   # nunca falla
    elif orden == "bajar":
        return bajar(argv[1:])
    elif orden == "fallo":
        fallo()
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
