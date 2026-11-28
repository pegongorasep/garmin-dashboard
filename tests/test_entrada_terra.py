"""Regresiones de entrada libre y plan sin reloj con fechas deterministas."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import nivel
import semanal
from dashboard import build
from test_build import CONFIG_FIXTURE, fixture
from test_motor_v6_f5 import _acts, _cfg, crudo_de, plan_v6
from test_web_cuentas import csrf_de
from test_web_plan_nuevo import nueva, respuestas
from test_zonas_garmin import PROPIO
from web import calculo
from web.modelos import Ajustes, Plan, Subida, Usuario


def test_ventana_y_volumen_manual():
    hoy = datetime(2026, 11, 27)
    def carrera(dias, manual=False):
        return {"startTimeLocal": (hoy - timedelta(days=dias)).isoformat(), "duration": 1860,
                "manual": manual, "activityType": {"typeKey": "running"}}
    assert nivel.hay_corrida_garmin([carrera(55)], hoy)
    assert not nivel.hay_corrida_garmin([carrera(56), carrera(2, True)], hoy)
    resultado = nivel.nivel_desde_datos([carrera(2, True)], hoy)
    assert resultado["evidencia"]["minutos_sem_prom"] > 0
    assert resultado["evidencia"]["trote_continuo_min"] == 0
    relato = nivel.nivel_sin_reloj(resultado, 3, 31)
    assert relato["inicio_minutos"] == 70 and relato["nivel"] == "base"
    assert nivel.nivel_sin_reloj(resultado, 1, 1)["inicio_minutos"] == nivel.PISO_NIVEL["empezando"]


def test_formulario_respuestas_nivel_y_espera(web_ctx):
    uid, cl = nueva(web_ctx)
    r = cl.get('/plan/nuevo')
    valores = {"csrf": csrf_de(r.text), "nivel": "automatico", "frecuencia_actual": "3", "corrida_larga": "31"}
    r = cl.post('/plan/nuevo/preguntas', data=valores)
    assert r.status_code == 200 and 'name="nivel" value="base"' in r.text
    assert 'name="corrida_larga" value="31"' in r.text
    regreso = cl.post('/plan/nuevo/nivel', data={**respuestas(dias='4'), **valores, 'nivel': 'base'})
    assert 'name="corrida_larga" value="31"' in regreso.text
    assert 'name="dias" value="4"' in regreso.text
    assert 'value="base" checked' in regreso.text
    form = {**respuestas(), **valores, "nivel": "corredor"}
    r = cl.post('/plan/nuevo/vista', data=form)
    assert r.status_code == 200 and 'tus datos dicen Base' in r.text
    assert 'name="frecuencia_actual" value="3"' in r.text
    r = cl.post('/plan/nuevo/confirmar', data=form, follow_redirects=False)
    assert r.status_code == 303
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid).plan['meta']['inicio_minutos'] >= nivel.PISO_NIVEL['corredor']
        u = db.get(Usuario, uid)
        u.repo_id, u.historial_pendiente = 77, True
        db.commit()
    r = cl.get('/plan/nuevo')
    assert 'descarga de tu historial' in r.text and 'action="/plan/nuevo/preguntas"' not in r.text


def test_ultima_subida_y_estado_real(web_ctx):
    uid, _ = nueva(web_ctx)
    ahora = datetime(2026, 11, 27, 18)
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        vacia = calculo.calcular(db, u, ahora)
        assert vacia['datos_al'] is None and vacia['hoy']['tarjeta']['tipo'] != 'primera_sync'
        assert 'zonas_garmin' not in vacia['ui']['avisos']
        u.repo_id, u.repo, u.historial_pendiente = 1, 'x/y', True
        db.commit()
        esperando = calculo.calcular(db, u, ahora)
        assert esperando['datos_al'] is None and esperando['hoy']['tarjeta']['tipo'] != 'primera_sync'
        db.add(Subida(usuario_id=uid, fecha=datetime(2026, 11, 27, 17), ok=True))
        db.commit()
        subida = calculo.calcular(db, u, ahora)
        assert subida['datos_al'].startswith('2026-11-27T11:00')
        assert subida['hoy']['tarjeta']['tipo'] == 'primera_sync'
        u.historial_pendiente = False
        db.commit()
        lista = calculo.calcular(db, u, ahora)
        assert lista['hoy']['tarjeta']['tipo'] != 'primera_sync'
        u.repo_id = None
        db.commit()
        assert calculo.calcular(db, u, ahora)['datos_al'] is None


def test_zonas_del_plan_solo_con_rangos_reales():
    datos = fixture()
    plan = build.load(build.ROOT / 'plan' / 'plan.example.json')
    ahora = datetime(2026, 11, 4, 12, tzinfo=ZoneInfo('America/Merida'))
    cfg = {**CONFIG_FIXTURE, 'modo': 'web'}
    sin = build.build({**datos, 'hr_zones': []}, plan, cfg, ahora)
    con = build.build({**datos, 'hr_zones': [PROPIO]}, plan, cfg, ahora)
    def pasos(out):
        return [p for w in out['plan']['semanas'] for s in w['sessions'] for p in s['steps'] if p['kind'] != 'repeat']
    assert pasos(sin) and all(p['lpm'] is None for p in pasos(sin))
    assert con['ui']['zonas_origen'] == 'garmin'
    assert any(p['lpm'] for p in pasos(con))


def test_recordatorio_se_oculta_a_coach_sin_edicion_y_con_garmin(web_ctx):
    uid, _ = nueva(web_ctx)
    plan = plan_v6()
    for sesion in plan['weeks'][1]['sessions']:
        sesion['dia'] = 0
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.sin_plan = False
        db.add(Ajustes(usuario_id=uid, config=crudo_de(plan)))
        db.add(Plan(usuario_id=uid, plan=plan))
        db.commit()
        instante = datetime(2026, 12, 8, 6, 1)  # 00:01 en Mérida, martes
        assert calculo.calcular(db, u, instante, pref='/a/1', editable=False)['ui']['recordatorio_corrida'] is None
        aviso = calculo.calcular(db, u, instante, pref='/a/1', editable=True)['ui']['recordatorio_corrida']
        assert aviso['fecha'] == '2026-12-08' and aviso['url'].startswith('/a/1/')
        u.repo_id, u.repo = 1, 'x/y'
        db.commit()
        assert calculo.calcular(db, u, instante)['ui']['recordatorio_corrida'] is None


def test_franja_doble_clic_get_anterior_403_y_red():
    import shutil
    import subprocess
    from pathlib import Path
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('Node no está instalado')
    raiz = Path(__file__).resolve().parent.parent
    subprocess.run([node, str(raiz / 'tests/fixtures/franja_carrera.js'), str(raiz / 'site/franja.js')], check=True, timeout=10)
