"""Revisa site/data.json antes de publicar: existe, es JSON, trae las claves esperadas y ninguna prohibida.

Uso: python dashboard/validar.py [ruta/data.json]   (sale con código 1 y explica qué falló)
No corre pytest: eso es del repo de Pedro.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
# Claves de primer nivel que puede tener data.json (lista blanca).
CLAVES = {"generado", "datos_al", "zonas", "rhr_promedio_7d", "aviso_zonas", "hoy", "ultima_corrida", "semana",
          "semanas_hoy", "semana_hoy_idx", "plan", "progreso", "composicion", "detalles", "ui",
          "carreras", "mejores_marcas", "tipos", "ayuda",
          "avisos"}   # avisos: solo la web, [{id, texto, fecha, url relativa}]
# Los de site/iconos.js: los del sistema de diseño (diseno/iconos) más los de siempre por si falta la carpeta.
ICONOS = {"correr", "medalla", "mancuerna", "rayo", "bici", "nadar", "caminar", "yoga", "punto"} | {
    f.stem for f in (ROOT / "diseno" / "iconos").glob("*.svg")}
OBLIGATORIAS = {"generado", "zonas", "hoy", "plan", "progreso", "detalles", "ui", "semanas_hoy"}
# Nada de esto puede aparecer como clave en ningún nivel: IDs de Garmin, nombres, GPS, tramos crudos.
PROHIBIDAS = {"activityId", "activityName", "ownerDisplayName", "ownerFullName", "userProfilePk", "userProfilePK",
              "userProfileId", "uuid", "activityUUID", "displayName", "locationName", "profileImageUrl",
              "ownerProfileImageUrlSmall", "fullName", "emailAddress", "birthDate", "dateOfBirth",
              "startLatitude", "startLongitude", "endLatitude", "endLongitude", "splitSummaries", "splits", "serie"}   # `serie` = FC por segundo: nunca se publica


# Ligas que el banner `ui.repo_estado` puede traer (a GitHub y a la página de la key de Garmin); ninguna otra URL.
PREFIJOS_LIGAS = ("https://github.com/", "https://connect.garmin.com/app/settings/")


def problemas(datos: dict) -> list:
    out = []
    if not isinstance(datos, dict):
        return ["data.json no es un objeto"]
    faltan = OBLIGATORIAS - set(datos)
    sobran = set(datos) - CLAVES
    if faltan:
        out.append(f"faltan claves: {', '.join(sorted(faltan))}")
    if sobran:
        out.append(f"claves fuera de la lista blanca: {', '.join(sorted(sobran))}")
    permitida = (datos.get("ui") or {}).get("acciones_url")

    def recorrer(o, ruta):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in PROHIBIDAS:
                    out.append(f"clave prohibida: {ruta}/{k}")
                if k == "icono" and v is not None and v not in ICONOS:
                    out.append(f"ícono desconocido: {ruta}/{k} = {v!r}")
                recorrer(v, f"{ruta}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                recorrer(v, f"{ruta}[{i}]")
        elif isinstance(o, str) and o.startswith("http") and o != permitida and not (
                ruta.startswith("/ui/repo_estado/") and o.startswith(PREFIJOS_LIGAS)):
            out.append(f"URL en el JSON: {ruta}")
    recorrer(datos, "")
    return out


def main() -> int:
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site" / "data.json"
    if not ruta.exists():
        print(f"ERROR: no existe {ruta}")
        return 1
    try:
        datos = json.loads(ruta.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: {ruta} no es JSON válido: {e}")
        return 1
    fallas = problemas(datos)
    for f in fallas:
        print(f"ERROR: {f}")
    if not fallas:
        print(f"OK: {ruta} cumple la lista blanca ({ruta.stat().st_size / 1024:.1f} KB)")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
