"""Animaciones A3: Progreso sin corridas en sus tres estados (ui.vacios.progreso y lo que pinta el sitio)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ayudas import crear_usuario, dar, entrar, listo
from dashboard import validar
from web import primer_inicio
from web.modelos import AvisoOculto, Usuario

SITE = Path(__file__).resolve().parent.parent / "site"
CONECTAR = {"texto": "sitio.prog.conectar", "href": "/bienvenida"}
REGISTRAR = {"texto": "sitio.prog.registrar", "href": "/actividad/nueva"}


def progreso(cl, url="/data.json"):
    d = cl.get(url).json()
    assert validar.problemas(d) == []
    return d["ui"]["vacios"]["progreso"]


def cuenta(ctx, correo="p@x.com"):
    uid = crear_usuario(ctx, correo, con_ajustes=True)
    return uid, entrar(ctx, ctx.cliente(), correo)


def vincular(ctx, uid):
    with ctx.sesiones() as db:
        db.get(Usuario, uid).repo_id = 100 + uid
        db.commit()


def historial(ctx, uid, pendiente):
    with ctx.sesiones() as db:
        db.get(Usuario, uid).historial_pendiente = pendiente
        db.commit()


def saltar(ctx, uid):
    with ctx.sesiones() as db:
        db.add(AvisoOculto(usuario_id=uid, aviso_id=primer_inicio.AVISO_GARMIN, huella="0"))
        db.commit()


def test_los_tres_estados(web_ctx):
    uid, cl = cuenta(web_ctx)
    assert progreso(cl) == {"estado": "sin_garmin", "conectar": "/bienvenida", "registrar": "/actividad/nueva"}
    vincular(web_ctx, uid)
    historial(web_ctx, uid, True)
    assert progreso(cl) == {"estado": "esperando", "conectar": None, "registrar": None}
    historial(web_ctx, uid, False)   # fuera de la caché: se ve al momento
    assert progreso(cl) == {"estado": "sin_corridas", "conectar": None, "registrar": "/actividad/nueva"}


def test_garmin_saltado_solo_ofrece_registrar(web_ctx):
    uid, cl = cuenta(web_ctx)
    saltar(web_ctx, uid)
    assert progreso(cl) == {"estado": "sin_garmin", "conectar": None, "registrar": "/actividad/nueva"}
    vincular(web_ctx, uid)   # si después conecta, manda lo que dice la conexión
    historial(web_ctx, uid, True)
    assert progreso(cl)["estado"] == "esperando"


def test_coach_con_y_sin_permiso(web_ctx):
    uid, atl = listo(web_ctx, "atl@x.com")
    _, coach = listo(web_ctx, "coach@x.com", con_plan=False)
    dar(atl, "coach@x.com")
    url = f"/a/{uid}/data.json"
    registrar = f"/a/{uid}/actividad/nueva"
    assert progreso(coach, url) == {"estado": "sin_garmin", "conectar": None, "registrar": registrar}   # conectar es solo del atleta
    vincular(web_ctx, uid)
    assert progreso(coach, url) == {"estado": "sin_corridas", "conectar": None, "registrar": registrar}
    with web_ctx.sesiones() as db:
        for pendiente, estado in ((False, "sin_corridas"), (True, "esperando")):
            u = db.get(Usuario, uid)
            u.historial_pendiente = pendiente
            v = primer_inicio.vacios(db, u, False, f"/a/{uid}", editable=False)["progreso"]
            assert v == {"estado": estado, "conectar": None, "registrar": None}
        u.repo_id = None
        v = primer_inicio.vacios(db, u, False, f"/a/{uid}", editable=False)["progreso"]
        assert v == {"estado": "sin_garmin", "conectar": None, "registrar": None}


def _pintado(vacios):
    """Lo que arma progresoVacio() (node, con stubs) con ese ui.vacios."""
    src = (SITE / "vista_progreso.js").read_text(encoding="utf-8")
    fuente = src[src.index("function progresoVacio("):src.index("function renderProgreso(")]
    js = """
const T=(k)=>k; const ui=()=>(%s); const DS={tarjeta:(o,x)=>({o,x}),estadoVacio:(o)=>o}; const ARTE={grafica:(o)=>o};
%s
console.log(JSON.stringify(progresoVacio()));
""" % (json.dumps({"vacios": vacios} if vacios is not None else {}), fuente)
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="sin node")
@pytest.mark.parametrize("estado,conectar,registrar,accion,secundaria", [
    ("sin_garmin", "/bienvenida", "/actividad/nueva", CONECTAR, REGISTRAR),
    ("sin_garmin", None, "/actividad/nueva", REGISTRAR, None),   # saltado o coach con permiso
    ("sin_garmin", None, None, None, None),                      # coach sin permiso
    ("esperando", None, None, None, None),
    ("sin_corridas", None, "/actividad/nueva", REGISTRAR, None),
])
def test_el_sitio_pinta_lo_que_dice_python(estado, conectar, registrar, accion, secundaria):
    r = _pintado({"progreso": {"estado": estado, "conectar": conectar, "registrar": registrar}})
    v, espera = r["x"], estado == "esperando"
    assert "titulo" not in r["o"]   # el título va una sola vez: el del estado vacío
    assert v["titulo"] == f"sitio.prog.{estado}_t" and v["texto"] == f"sitio.prog.{estado}_x"
    assert v["accion"] == accion and v["secundaria"] == secundaria
    assert v["arte"] == {"espera": espera} and v["espera"] is espera and v["unaVez"] == (None if espera else "progreso")


@pytest.mark.skipif(not shutil.which("node"), reason="sin node")
@pytest.mark.parametrize("vacios", [None, {"plan": None}])
def test_sin_la_clave_nueva_sale_la_tarjeta_de_antes(vacios):
    r = _pintado(vacios)
    assert r["o"]["titulo"] == "sitio.cp.titulo"
    assert r["x"] == {"icono": None, "titulo": "sitio.cp.vacio_t", "texto": "sitio.cp.vacio_x"}
