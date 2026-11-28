"""Ayudas compartidas entre archivos de pruebas (no son pruebas ni fixtures)."""
import json
import re
from pathlib import Path
from datetime import timedelta
from dashboard.ajustes import leer_config_yaml
from web.modelos import Ajustes, Consentimiento, Usuario
from web.privacidad import VERSION_AVISO
from datetime import date, datetime
from web.modelos import DatoGarmin
import copy
from datetime import timezone
import planes_v6
from dashboard.ajustes import normalizar_config
from web.modelos import Plan
from web.modelos import Sincronizacion
import gzip
import time
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from zoneinfo import ZoneInfo
from dashboard.ajustes import cargar_config
from plan import motor_v6
from web import plan_vivo
from plan import motor_v6 as v6
from web import oauth
from urllib.parse import parse_qs, urlparse
from web.github_app import GitHubError
import io
from PIL import Image

ROOT = Path(__file__).parent.parent
ISS = "https://token.actions.githubusercontent.com"
WORKFLOW = "pegongorasep/garmin-dashboard/.github/workflows/motor.yml@refs/tags/stable"
LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTRA_LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks_falso():
    jwk = json.loads(RSAAlgorithm.to_jwk(LLAVE.public_key()))
    jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


# --- de test_web_cuentas
CONFIG = json.loads(json.dumps(leer_config_yaml(Path(__file__).parent / "fixtures" / "config.yaml"), default=str))


def csrf_de(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def post(cl, url, **campos):
    """GET a la página (para la cookie y el token CSRF) y luego POST con el token."""
    r = cl.get(url)
    return cl.post(url, data={"csrf": csrf_de(r.text), **campos})


def liga_de(ctx) -> str:
    return re.search(r"https://ahilallevas\.test(/entrar/liga/\S+)", ctx.enviados[-1][2]).group(1)


def codigo_de(ctx) -> str:
    return re.search(r"entrar a Ahí la Llevas: (\d{6}) \(vale 10 minutos\)", ctx.enviados[-1][2]).group(1)


def entrar(ctx, cl, correo):
    post(cl, "/entrar", correo=correo)
    con_codigo(cl, correo, codigo_de(ctx))
    return cl


def crear_usuario(ctx, correo="a@x.com", con_ajustes=False):
    with ctx.sesiones() as db:
        u = Usuario(correo=correo, nombre="Ana", apellido="Prueba")
        db.add(u)
        db.commit()
        if con_ajustes:
            db.add(Ajustes(usuario_id=u.id, config=CONFIG))
            db.add(Consentimiento(usuario_id=u.id, version_aviso=VERSION_AVISO))
            db.commit()
        return u.id


# --- de test_web_feed
def dia(i):
    return (date.today() - timedelta(days=i)).isoformat()


def act(cat="run", minutos=40, km=5.0, sesion=None, manual=False):
    return {"cat": cat, "nombre": "Corrida" if cat == "run" else "Fuerza", "icono": "correr" if cat == "run" else "mancuerna",
            "minutos": minutos, "km": km, "fc_prom": 140, "carrera": False, "sesion": sesion, "partes": [], "esfuerzo": 3, "rpe": None,
            "trote": None, "manual": manual, "detalle": {"fc_max": 160, "zonas": None, "kcal": 300}}


def falso_calcular(por_usuario):
    """calcular(db, u) -> data.json mínimo con las actividades dadas {uid: [(días atrás, actividad)]}."""
    def f(db, u, *a, **k):
        dias = {}
        for i, ac in por_usuario.get(u.id, []):
            dias.setdefault(dia(i), []).append(ac)
        return {"semanas_hoy": [{"n": 3, "dias": [{"fecha": d, "actividades": v} for d, v in dias.items()]}]}
    return f


def uid_de(ctx, correo):
    with ctx.sesiones() as db:
        return db.query(Usuario).filter_by(correo=correo).one().id


def tres(web_ctx):
    """a y b en un grupo; c sin grupo."""
    a, b, c = (sesion_grupos(web_ctx, f"{x}@x.com") for x in "abc")
    gid = crear(a)
    post_grupos(b, f"/grupos/unirse/{liga(a, gid)}")
    return a, b, c, gid


def ids_feed(cl, **q):
    r = cl.get("/api/juntos/feed", params=q)
    assert r.status_code == 200
    return r.json()


# --- de test_web_grupos
def sesion_grupos(ctx, correo):
    crear_usuario(ctx, correo)
    return entrar(ctx, ctx.cliente(), correo)


def post_grupos(cl, url, **campos):
    return cl.post(url, data={"csrf": csrf_de(cl.get("/grupos/nuevo").text), **campos})


def crear(cl, nombre="Los Fieras"):
    r = post_grupos(cl, "/grupos/nuevo", nombre=nombre)
    assert r.status_code == 303
    return int(r.headers["location"].rsplit("/", 1)[1])


def liga(cl, gid):
    t = post_grupos(cl, f"/grupos/{gid}/invitar").text
    return re.search(r"/grupos/unirse/([\w-]+)", t).group(1)


# --- de test_web_ajustes
HOY = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)   # miércoles de la semana 3 (el plan empieza el 2026-11-09)


def tok(cl):
    return csrf_de(cl.get("/ajustes").text)


def listo(ctx, correo="a@x.com", con_plan=True):
    """Usuario con consentimiento, ajustes y plan; devuelve (id, cliente con sesión)."""
    ctx.app.state.reloj = lambda: HOY
    with ctx.sesiones() as db:
        u = Usuario(correo=correo, nombre="Ana", apellido="Prueba")
        db.add(u)
        db.commit()
        db.add(Ajustes(usuario_id=u.id, config=copy.deepcopy(CONFIG)))
        db.add(Consentimiento(usuario_id=u.id, version_aviso=VERSION_AVISO))
        db.add(DatoGarmin(usuario_id=u.id, tipo="dia", clave="2026-11-24",   # algo de datos: si no, la tarjeta de hoy es «primera sincronización»
                          contenido={"calendarDate": "2026-11-24", "heartRate": {"restingValue": 55}}))
        if con_plan:
            db.add(Plan(usuario_id=u.id, plan=planes_v6.generar(normalizar_config(CONFIG))))
        db.commit()
        uid = u.id
    return uid, entrar(ctx, ctx.cliente(), correo)


def guardar(cl, url="/ajustes", **cambia):
    r = cl.get(url)
    return cl.post(url, data={"csrf": csrf_de(r.text), **form_ajustes(**cambia)})


def crudo(ctx, uid):
    with ctx.sesiones() as db:
        return copy.deepcopy(db.get(Ajustes, uid).config)


def plan_de(ctx, uid):
    with ctx.sesiones() as db:
        return copy.deepcopy(db.get(Plan, uid).plan)


# --- de test_sincronizar
V2 = {"motor_version": 2}


def _instr(ctx, cuerpo=None, **claims):
    return ctx.cliente().post("/api/tubo/instrucciones", json=cuerpo, headers=auth_tubo(token_tubo(ctx, **claims)))


def _sincs(ctx):
    with ctx.sesiones() as db:
        return [(s.tipo, s.estado, s.paso, s.run_id, s.hechos, s.total, s.error, s.nuevas)
                for s in db.query(Sincronizacion).order_by(Sincronizacion.id)]


# --- de test_web_tubo
def token_tubo(web_ctx, llave=LLAVE, **extra):
    claims = {"iss": ISS, "aud": web_ctx.settings.oidc_audience, "exp": int(time.time()) + 600,
              "repository": "amigo/garmin-prueba", "repository_id": "777", "repository_owner": "Amigo",
              "repository_owner_id": "5", "repository_visibility": "private", "job_workflow_ref": WORKFLOW, **extra}
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, llave, algorithm="RS256", headers={"kid": "k1"})


def usuario_amigo(ctx, owner="amigo", consentimiento=True, repo_id=None):
    with ctx.sesiones() as db:
        u = Usuario(correo="amigo@x.com", nombre="Ana", apellido="Prueba", github_owner=owner, repo_id=repo_id, repo="amigo/garmin-prueba" if repo_id else None)
        db.add(u)
        db.commit()
        if consentimiento:
            db.add(Consentimiento(usuario_id=u.id, version_aviso=VERSION_AVISO))
            db.commit()
        return u.id


def auth_tubo(tok):
    return {"Authorization": f"Bearer {tok}"}


def paquete_chico(**cambios):
    pq = {"esquema": 1, "motor": "abc123", "archivos": {
        "daily": {"daily_summaries": [{"calendarDate": "2026-11-01", "heartRate": {"restingValue": 60}}], "sleep": [], "hrv": []},
        "activities": [{"id": "a1", "es_carrera": False, "startTimeLocal": "2026-11-01 07:00:00",
                        "activityType": {"typeKey": "running"}, "duration": 1200.0, "distance": 3000.0}],
        "activity_details": {"a1": {"rpe": 3.0, "serie": [[0, 0, 100]]}}, "hr_zones": [{"sport": "DEFAULT", "maxHeartRateUsed": 190}],
        "historial_corridas": [], "meta": {"pulled_at": "2026-11-01", "pulled_at_utc": "2026-11-01T12:00:00+00:00"}}}
    pq.update(cambios)
    return pq


def subir(cl, tok, pq, comprimir=True):
    cuerpo = json.dumps(pq).encode()
    cab = auth_tubo(tok)
    if comprimir:
        cuerpo, cab = gzip.compress(cuerpo), {**cab, "Content-Encoding": "gzip"}
    return cl.post("/api/tubo/subida", content=cuerpo, headers={**cab, "Content-Type": "application/json"})


class RespuestaFalsa:
    def __init__(self, status=200, cuerpo=None):
        self.status_code, self._c = status, cuerpo or {}

    def json(self):
        return self._c

    def raise_for_status(self):
        pass


class HttpFalso:
    def __init__(self, post, get=None):
        self._post, self._get, self.llamadas = post, get, []

    def post(self, url, **kw):
        self.llamadas.append(("post", url, kw))
        return self._post(url, **kw)

    def get(self, url, **kw):
        self.llamadas.append(("get", url, kw))
        return self._get(url, **kw)


ENTORNO = {"ACTIONS_ID_TOKEN_REQUEST_URL": "https://actions.example/t?x=1", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "tok",
           "GITHUB_REPOSITORY_ID": "777"}


# --- de test_build
CONFIG_BUILD = cargar_config(ROOT / "tests" / "fixtures")


CONFIG_FIXTURE = {**CONFIG_BUILD, "plan_start": "2026-10-26"}


AHORA = datetime(2026, 11, 4, 12, 0, tzinfo=ZoneInfo("America/Merida"))  # miércoles, semana 2


def fixture():
    def act(i, dia, tipo, **kw):
        return {"activityId": i, "activityUUID": f"uuid-{i}", "activityName": "Corrida de Calle Secreta",
                "ownerDisplayName": "Persona Inventada", "ownerFullName": "Persona Inventada",
                "userProfilePk": 99, "locationName": "Calle Secreta",
                "ownerProfileImageUrlSmall": "https://ejemplo.com/foto.png",
                "startTimeLocal": f"{dia} 18:00:00", "duration": 1800.0,
                "activityType": {"typeKey": tipo}, "averageHR": 140.0, "averageSpeed": 3.0,
                "maxHR": 180.0, "hrTimeInZone_1": 300, "hrTimeInZone_2": 900, "hrTimeInZone_3": 300,
                "hrTimeInZone_4": 0, "hrTimeInZone_5": 0, "distance": 4500.0, **kw}
    tramos = [{"splitType": "RWD_RUN", "duration": 1200.0, "distance": 3000.0, "noOfSplits": 3},
              {"splitType": "RWD_WALK", "duration": 600.0, "distance": 700.0, "noOfSplits": 3}]
    dias = [f"2026-10-{d:02d}" for d in range(20, 32)] + ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"]
    return {
        "daily_summaries": [{"calendarDate": d, "displayName": "Persona Inventada",
                             "heartRate": {"restingValue": 60}} for d in dias],
        "sleep": [{"calendarDate": d, "sleepTimeSeconds": 25000, "userProfilePK": 99} for d in dias],
        "hrv": [{"calendarDate": d, "lastNightAvg": 34, "status": "BALANCED",
                 "baseline": {"lowUpper": 28, "balancedLow": 30, "balancedUpper": 38}} for d in dias],
        "activities": [act(1, "2026-11-02", "hiit"), act(2, "2026-11-03", "running", splitSummaries=tramos),
                       act(3, "2026-10-28", "running", splitSummaries=tramos, endLatitude=1.0, endLongitude=2.0),
                       act(4, "2026-11-03", "hiit")],
        "details": {"1": {"rpe": 6.0, "feel": 50},
                    "2": {"rpe": 4.0, "feel": 50, "splits": [
                        {"tipo": "RWD_RUN", "seg": 1200.0, "m": 3000.0, "fc": 145.0, "n": 3},
                        {"tipo": "RWD_WALK", "seg": 600.0, "m": 700.0, "fc": 125.0, "n": 3}]},
                    "3": {"rpe": None, "feel": None}},
        "hr_zones": [{"sport": "DEFAULT", "maxHeartRateUsed": 190, "restingHeartRateUsed": 64, "zone1Floor": 125, "zone2Floor": 138,
                      "zone3Floor": 151, "zone4Floor": 164, "zone5Floor": 177}],   # zonas de Garmin (la web solo pinta lpm con ellas)
        "meta": {"pulled_at_utc": "2026-11-04T17:00:00+00:00"},
    }


# --- de test_motor_v6_f5
INICIO = date(2026, 11, 30)   # lunes


def plan_v6(**extra):
    return motor_v6.generar_v6({"nivel": "base", "dias": 3, "meta": "base", "inicio": INICIO.isoformat(), "evidencia": EV,
                                "inicio_minutos": 60, "semanas": 12, **extra})


def crudo_de(plan, **corrida):
    return {"perfil": {"edad": 35, "zona_horaria": "America/Merida"}, "corrida": {"inicio": plan["start"], "semanas": len(plan["weeks"]), **corrida}}


def _acts(minutos_por_semana: dict):
    out = []
    for i, mins in minutos_por_semana.items():
        for k in range(3):
            f = INICIO + timedelta(weeks=i, days=2 * k)
            out.append({"startTimeLocal": f"{f} 07:00:00", "duration": mins / 3 * 60, "activityType": {"typeKey": "running"}})
    return out


def _cfg(plan):
    return {"plan_start": plan["start"], "semanas_repetidas": [], "pausas": [], "plan_semanas": len(plan["weeks"]),
            **{k: v for k, v in normalizar_config(crudo_de(plan)).items()}}


# --- de test_web_plan_nuevo
def lunes_siguiente() -> date:
    hoy = date.today()
    return hoy + timedelta(days=(7 - hoy.weekday()) % 7 or 7)


def respuestas(**extra):
    return {"dias": "3", "frecuencia_actual": "3", "corrida_larga": "5", "inicio": lunes_siguiente().isoformat(), "edad": "35", "zona": "America/Merida", **extra}


def confirmar(cl, nivel, pref="", **extra):
    r = preguntas(cl, nivel, pref)
    return cl.post(f"{pref}/plan/nuevo/confirmar", data={"csrf": csrf_de(r.text), "nivel": nivel, **respuestas(**extra)})


def nueva(web_ctx, correo="n@x.com"):
    uid = crear_usuario(web_ctx, correo)
    return uid, entrar(web_ctx, web_ctx.cliente(), correo)


# --- de test_zonas_garmin
PROPIO = {"sport": "RUNNING", "trainingMethod": "HR_RESERVE", "restingHeartRateUsed": 55, "lactateThresholdHeartRateUsed": 172,
          "zone1Floor": 118, "zone2Floor": 132, "zone3Floor": 146, "zone4Floor": 160, "zone5Floor": 174, "maxHeartRateUsed": 190}


# --- de test_planes_saltos
def crudo_con(corrida=None, **resto):
    c = copy.deepcopy(CONFIG)
    c["corrida"] = {**c["corrida"], **(corrida or {})}
    return {**c, **resto}


INI = date(2026, 11, 9)
HOY_SALTOS = INI + timedelta(weeks=4, days=2)   # miércoles de la semana 5 del plan que empieza en INI


def cfg_de(crudo, hoy=HOY_SALTOS):
    return plan_vivo.con_pausas(normalizar_config(crudo), hoy)


def plan_carrera(km=10, hasta=14):
    return v6.generar_v6(entrada(inicio=INI.isoformat(), meta={"km": km, "semanas_hasta": hasta}))


def crudo_carrera(plan):
    return crudo_con({"semanas": len(plan["weeks"]),
                      "metas": [{"id": "c1", "tipo": "carrera", "fecha": "2027-02-14", "distancia_km": 10, "nombre": "10K", "en_plan": True}]})


# --- de test_web_mcp
def token_para(web_ctx, uid):
    with web_ctx.sesiones() as db:
        ahora = web_ctx.app.state.reloj().replace(tzinfo=None)
        t, _ = oauth._tokens_nuevos(db, None, ahora, client_id="c", usuario_id=uid, resource="https://ahilallevas.test/mcp")
        db.commit()
        return t["access_token"]


def rpc(cl, token, metodo, params=None, id_=1, ruta="/mcp"):   # la URL tal cual la usan Claude y ChatGPT
    h = dict(HEAD)
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = cl.post(ruta, headers=h, json={"jsonrpc": "2.0", "id": id_, "method": metodo, "params": params or {}})
    return r


def cuerpo(r):
    txt = r.text
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        txt = next(l[5:] for l in txt.splitlines() if l.startswith("data:"))
    return json.loads(txt)


def llamar(cl, token, herramienta, **args):
    r = rpc(cl, token, "tools/call", {"name": herramienta, "arguments": args})
    assert r.status_code == 200, r.text
    res = cuerpo(r)["result"]
    return res.get("isError", False), res["content"][0]["text"]


# --- de test_conexion
class Falsa:
    def __init__(self):
        self.instalaciones = [55]
        self.repos = [{"id": 900, "full_name": "ana/ahilallevas-datos", "private": True, "default_branch": "main"}]
        self.falla_disparo = False
        self.disparos = []

    def url_instalar(self, state):
        return f"https://github.com/apps/x/installations/new?state={state}"

    def token_de_usuario(self, code):
        if code == "mala":
            raise GitHubError(400, "bad_verification_code")
        return "TOKEN-SECRETO-USUARIO"

    def instalaciones_del_usuario(self, token):
        return self.instalaciones

    def repos_de_instalacion(self, inst):
        return self.repos

    def disparar(self, inst, repo, rama, workflow="deploy.yml"):
        if self.falla_disparo:
            raise GitHubError(500, "x")
        self.disparos.append((inst, repo, rama))
        return True


def sesion(ctx, correo="ana@x.com"):
    uid = usuario_amigo(ctx, owner="ana", consentimiento=True)
    with ctx.sesiones() as db:
        db.get(Usuario, uid).correo = correo
        db.commit()
    cl = ctx.cliente()
    entrar(ctx, cl, correo)
    return cl, uid


def empezar(cl, para=None):
    r = cl.get("/conectar/github" + (f"?para={para}" if para else ""))
    assert r.status_code == 303
    return parse_qs(urlparse(r.headers["location"]).query)["state"][0]


def volver(cl, state, code="bueno", inst="55"):
    return cl.get("/conectar/github/vuelta", params={"state": state, "code": code, "installation_id": inst,
                                                     "setup_action": "install"})


# --- de test_guia
def conectada(ctx, gh):
    cl, uid = sesion(ctx)
    volver(cl, empezar(cl))
    return cl, uid


def token_guia(cl):
    return csrf_de(cl.get("/bienvenida").text)


# --- de test_garmin_ajustes
def con_ajustes(ctx, uid):
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.repo, u.repo_id = "ana/ahilallevas-datos", 900
        db.add(Ajustes(usuario_id=uid, config=copy.deepcopy(CONFIG)))
        db.add(DatoGarmin(usuario_id=uid, tipo="dia", clave="2026-11-24", contenido={"calendarDate": "2026-11-24"}))
        db.commit()


# --- de test_web_coach
def dar(cl, correo):
    return cl.post("/coach/dar", data={"csrf": csrf_de(cl.get("/coach").text), "correo": correo})


# --- de test_web_actividad
def datos(**kw):
    return {"tipo": "correr", "fecha": "2026-11-24", "distancia": "5", "tiempo": "30:00", **kw}


def enviar(cl, url, form, ir=None):
    r = cl.get(ir or url)
    return cl.post(url, data={"csrf": csrf_de(r.text), **form}, follow_redirects=False)


# --- de test_motor_v6
def entrada(**kw):
    return {"nivel": "base", "dias": 3, "inicio": LUNES, "inicio_minutos": 100, "evidencia": dict(EV_BASE), "edad": 35, **kw}


# --- de test_web_solo_cuerpo
def nuevo(ctx, correo="c@x.com", uso=None, consentido=True):
    uid = crear_usuario(ctx, correo)
    with ctx.sesiones() as db:
        if consentido:
            db.add(Consentimiento(usuario_id=uid, version_aviso=VERSION_AVISO))
        db.get(Usuario, uid).uso = uso
        db.commit()
    return uid, entrar(ctx, ctx.cliente(), correo)


def token_cuerpo(cl, url="/bienvenida"):
    return csrf_de(cl.get(url).text)


# --- de test_web_perfil
def con_exif_gps(color=(200, 30, 30), tam=(640, 480), formato="JPEG") -> bytes:
    im = Image.new("RGB", tam, color)
    exif = Image.Exif()
    exif[0x010F] = "CamaraSecreta"   # Make
    exif[0x8825] = {1: "N", 2: (20.0, 58.0, 0.0), 3: "W", 4: (89.0, 37.0, 0.0)}   # GPS
    b = io.BytesIO()
    im.save(b, formato, exif=exif.tobytes()) if formato == "JPEG" else im.save(b, formato)
    return b.getvalue()


# --- de test_web_cuentas (dependencias)
def con_codigo(cl, correo, codigo):
    return cl.post("/entrar/codigo", data={"csrf": csrf_de(cl.get("/entrar").text), "correo": correo, "codigo": codigo})


# --- de test_web_ajustes (dependencias)
def form_ajustes(**cambia):
    """Formulario de Ajustes (solo lo general)."""
    base = {"titulo": "Mi entreno", "zona": "America/Merida", "edad": "29", "fc_max": "189", "sensor": "banda",
            "inbody": "on"}
    base.update(cambia)
    return {k: v for k, v in base.items() if v != ""} | {k: "" for k in ("fc_max",) if base[k] == ""}


# --- de test_web_plan_nuevo (dependencias)
def preguntas(cl, nivel, pref=""):
    r = cl.get(f"{pref}/plan/nuevo")
    return cl.post(f"{pref}/plan/nuevo/preguntas", data={"csrf": csrf_de(r.text), "nivel": nivel, "frecuencia_actual": "3", "corrida_larga": "5"})


# --- de test_planes_saltos (dependencias)


# --- de test_motor_v6_f5 (dependencias)
EV = {"minutos_sem_prom": 60, "trote_continuo_min": 30, "semanas_consistentes": 2, "sesion_max_30d": 30}


# --- de test_web_mcp (dependencias)
HEAD = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


# --- de test_motor_v6 (dependencias)
LUNES = "2026-11-30"


EV_BASE = {"semanas_consistentes": 8, "trote_continuo_min": 35, "minutos_sem_prom": 95, "sesion_max_30d": 35, "dias_intensos": []}


# --- de test_guia (dependencias)
class ConSecretos(Falsa):
    def __init__(self):
        super().__init__()
        self.secs = []
        self.falla_secretos = False

    def secretos(self, inst, repo):
        if self.falla_secretos:
            from web.github_app import GitHubError
            raise GitHubError(500, "x")
        return [{"name": n, "updated_at": None} for n in self.secs]
