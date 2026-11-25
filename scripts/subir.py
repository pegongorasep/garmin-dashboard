"""Lo corre `motor.yml` en el repo de cada persona: pide instrucciones a la web y le sube el paquete de data/.

Solo `requests` y la librería estándar (más dashboard/paquete.py del motor). NUNCA falla el workflow por culpa de la web:
si no responde, avisa y sigue (`publicar_pages=true`, como antes de la web).

  python subir.py instrucciones   imprime los argumentos para garmin_connect.py (vacío = los de siempre)
  python subir.py subir           arma el paquete de <GARMIN_USER_DIR>/data y lo sube; escribe publicar_pages=... en $GITHUB_OUTPUT

Variables: AHILALLEVAS_URL (la web), ACTIONS_ID_TOKEN_REQUEST_URL/TOKEN (las pone GitHub con `id-token: write`),
GITHUB_REPOSITORY_ID (la sal de los ids), GARMIN_USER_DIR, GITHUB_OUTPUT.
"""
import gzip
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

URL_POR_DEFECTO = "https://ahilallevas.com"
TIMEOUT = 60
REINTENTOS = 2
ESPERA = 5
ARGS_OK = re.compile(r"^(--dias-actividades [0-9]{1,4})?( --historial-desde [0-9]{4}-[0-9]{2}-[0-9]{2})?$")


def _url() -> str:
    return os.environ.get("AHILALLEVAS_URL", URL_POR_DEFECTO).rstrip("/")


def _avisa(texto: str) -> None:
    print(f"[ahi-la-llevas] {texto}", file=sys.stderr)


_codigo_escrito = set()


def _resumen_codigo(r) -> None:
    """Si la web respondió 403 con un código de vinculación, lo escribe en el resumen de la corrida
    ($GITHUB_STEP_SUMMARY): solo lo ven quienes tienen acceso al repo privado. No va al log común."""
    try:
        codigo = str(r.json().get("codigo") or "")
    except Exception:   # noqa: BLE001
        return
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if not (re.fullmatch(r"[0-9]{6}", codigo) and ruta) or codigo in _codigo_escrito:
        return
    _codigo_escrito.add(codigo)
    with open(ruta, "a") as f:
        f.write(f"## Ahí la Llevas\n\n**Tu código para Ahí la Llevas: {codigo}** (vence en 1 h)\n\n"
                "Escríbelo en la página de bienvenida de Ahí la Llevas para vincular este repo. "
                "Esta corrida no guardó datos: después de vincular, corre «Run workflow» otra vez.\n")
    _avisa("la web pidió vincular este repo: el código está en el resumen de la corrida (Summary)")


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
        r = _pedir("/api/tubo/instrucciones", b"{}", {"Authorization": f"Bearer {token_oidc(http=http)}",
                                                      "Content-Type": "application/json"}, http, dormir)
        if r.status_code != 200:
            _resumen_codigo(r)
            _avisa(f"la web no vinculó este repo (HTTP {r.status_code}); todo sigue como siempre")
            return ""
        d = r.json()
        args = []
        if d.get("dias_actividades"):
            args.append(f"--dias-actividades {int(d['dias_actividades'])}")
        if d.get("historial_desde"):
            args.append(f"--historial-desde {d['historial_desde']}")
        texto = " ".join(args)
        return texto if ARGS_OK.match(texto) else ""   # nunca se pasa al shell algo con otra forma
    except Exception as e:   # noqa: BLE001  (nunca falla el workflow)
        _avisa(f"no se pudieron pedir instrucciones a la web ({type(e).__name__}); se usan las de siempre")
        return ""


def subir(data_dir: Path, entorno=os.environ, http=requests, dormir=time.sleep) -> bool:
    """Sube el paquete. Devuelve `publicar_pages` (True si la web no respondió o no vinculó este repo)."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))
        import paquete
        pq = paquete.armar(data_dir, salt=entorno.get("GITHUB_REPOSITORY_ID", ""))
        problemas = paquete.validar(pq)
        if problemas:
            _avisa("el paquete no pasó la lista blanca, no se sube: " + "; ".join(problemas))
            return True
        cuerpo = gzip.compress(json.dumps(pq, separators=(",", ":")).encode())
        r = _pedir("/api/tubo/subida", cuerpo, {"Authorization": f"Bearer {token_oidc(entorno, http)}",
                                               "Content-Type": "application/json", "Content-Encoding": "gzip"}, http, dormir)
        if r.status_code == 200:
            publicar = bool(r.json().get("publicar_pages", True))
            print(f"[ahi-la-llevas] datos subidos ({len(cuerpo) / 1024:.0f} KB); publicar Pages: {publicar}")
            return publicar
        _resumen_codigo(r)
        _avisa(f"la web no aceptó el paquete (HTTP {r.status_code}); todo sigue como siempre")
    except Exception as e:   # noqa: BLE001
        _avisa(f"no se pudo subir a la web ({type(e).__name__}); todo sigue como siempre")
    return True


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    orden = argv[0] if argv else ""
    if orden == "instrucciones":
        print(instrucciones())
    elif orden == "subir":
        publicar = subir(Path(os.environ.get("GARMIN_USER_DIR") or ".") / "data")
        salida = os.environ.get("GITHUB_OUTPUT")
        linea = f"publicar_pages={'true' if publicar else 'false'}"
        if salida:
            with open(salida, "a") as f:
                f.write(linea + "\n")
        else:
            print(linea)
    else:
        print(__doc__)
    return 0   # siempre: la web nunca tumba el workflow


if __name__ == "__main__":
    sys.exit(main())
