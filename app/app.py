"""Mi Plan · registro por actividad y seguimiento (Streamlit). Funciona en la nube o en tu compu."""
from __future__ import annotations

import datetime as dt
import html
import os

import pandas as pd
import streamlit as st

import analisis as A
import core
import informe
from plan_io import TEST_REG_FIELDS, tests_objetos
from registro import ESTADOS, ICONO, TIPOS, UNIDAD, carga_act, parse_ok, resumen_act, ritmo_auto
from zonas import Zonas, calcular_base, mss, parse_time

st.set_page_config(page_title="Mi Plan", page_icon="🏃", layout="wide", initial_sidebar_state="collapsed")

# ------------------------------------------------------------------ estilo
st.markdown("""
<style>
:root{--navy:#122B43;--teal:#0F766E;--teal2:#E6F4F1;--muted:#6B7280;--line:#E5E7EB}
.block-container{padding-top:1.6rem;padding-bottom:4rem;max-width:1240px}
header[data-testid="stHeader"]{height:0;background:transparent}
h1,h2,h3,h4,h5{color:var(--navy)!important}
button[data-testid="stNumberInputStepUp"],button[data-testid="stNumberInputStepDown"]{display:none}
div[data-baseweb="tab-list"]{gap:2px;flex-wrap:nowrap;overflow-x:auto}
button[data-baseweb="tab"]{padding:8px 12px!important;border-radius:10px 10px 0 0}
button[data-baseweb="tab"] p{font-size:.98rem;font-weight:600}
.top{display:flex;align-items:flex-end;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.top .t{font-size:1.45rem;font-weight:800;color:var(--navy);line-height:1.15}
.top .s{color:var(--muted);font-size:.9rem}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.75rem;font-weight:700;background:#EEF2F7;color:#334155;margin-left:4px}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin-bottom:12px;box-shadow:0 1px 2px rgba(16,24,40,.04)}
.card h4{margin:0 0 8px;font-size:1rem}
.lbl{font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-top:8px;font-weight:600}
.txt{font-size:.95rem;color:#1F2937;line-height:1.35}
.obj{background:var(--teal2);color:#0B5E57;border-radius:9px;padding:7px 10px;font-weight:600;font-size:.88rem;margin-top:5px}
.chip{display:inline-block;padding:1px 9px;border-radius:999px;font-size:.7rem;font-weight:700;margin-left:6px;vertical-align:middle}
.muted{color:#9CA3AF}
.hero{border-radius:16px;padding:14px 16px;margin:6px 0 12px;border:1px solid}
.hero .n{font-size:1.15rem;font-weight:800}
.hero .d{font-size:.86rem;margin-top:4px}
.hero .m{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;font-size:.85rem}
.hero .m b{font-size:1.02rem}
.h-Listo{background:#ECFDF3;border-color:#ABEFC6;color:#05603A}
.h-Precaución{background:#FFFAEB;border-color:#FEDF89;color:#93370D}
.h-Recupera{background:#FEF3F2;border-color:#FECDCA;color:#912018}
.h-Sindatos{background:#F8FAFC;border-color:#E2E8F0;color:#475569}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:6px 0 14px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.kpi .l{font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}
.kpi .v{font-size:1.25rem;font-weight:800;color:var(--navy);margin-top:2px}
.kpi .s{font-size:.75rem;color:var(--muted)}
.act{display:flex;justify-content:space-between;align-items:center;gap:8px}
.act .a{font-weight:700;color:#1F2937}.act .b{font-size:.85rem;color:var(--muted)}
.sem-VERDE{background:#D1FADF;color:#05603A}.sem-AMARILLO{background:#FEF0C7;color:#93370D}
.sem-ROJO{background:#FEE4E2;color:#912018}.sem-SINREGISTRO{background:#F2F4F7;color:#475467}
.sec{font-size:1.02rem;font-weight:800;color:var(--navy);margin:14px 0 6px}
@media (max-width:640px){
 .block-container{padding-left:.8rem;padding-right:.8rem}
 .kpis{grid-template-columns:repeat(2,1fr)}
 .top .t{font-size:1.2rem}
 div[class*="st-key-fila"] div[data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:.45rem!important}
 div[class*="st-key-fila"] div[data-testid="stColumn"]{min-width:0!important;width:auto!important;flex:1 1 0!important}
 div[class*="st-key-fila_fecha"] div[data-testid="stColumn"]:nth-child(2),div[class*="st-key-fila_sem"] div[data-testid="stColumn"]:nth-child(2){flex:3.5 1 0!important}
 div[class*="st-key-fila_act"] div[data-testid="stColumn"]:first-child{flex:5 1 0!important}
}
</style>
""", unsafe_allow_html=True)

CHIP = {"TEST": ("#EDE9FE", "#5B21B6"), "CARRERA": ("#FEE4E2", "#912018"), "MEDIA": ("#FEE4E2", "#912018"),
        "RM": ("#DBEAFE", "#1E3A8A"), "UMBRAL": ("#FFEDD5", "#9A3412"), "TEMPO": ("#FFEDD5", "#9A3412"),
        "INTERVALOS": ("#FFEDD5", "#9A3412"), "CUESTAS": ("#FFEDD5", "#9A3412"), "FONDO": ("#CCFBF1", "#115E59"),
        "Z2": ("#DCFCE7", "#166534"), "BRICK": ("#DCFCE7", "#166534"), "BICI": ("#FFEDD5", "#9A3412"),
        "RECUPERACION": ("#F1F5F9", "#475569"), "DESCANSO": ("#F8FAFC", "#94A3B8")}
EST_ICON = {"Hecho": "✅", "Parcial": "🟡", "Omitido": "❌", "Cambiado": "🔁", "Plan": "▫️"}
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def dm(f, y=False):
    return f"{f.day} {MESES[f.month - 1]}" + (f" {f.year}" if y else "")


def larga(f):
    return f"{DIAS_ES[f.weekday()]} {f.day} {MESES[f.month - 1]} {f.year}"


def esc(v):
    return "" if vacio(v) else html.escape(str(v))


def vacio(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "—", "None", "nan", "NaT")


def tx(v):
    return "" if vacio(v) else str(v)


def chip(code):
    if vacio(code):
        return ""
    key = next((k for k in CHIP if str(code).startswith(k)), None)
    bg, fg = CHIP.get(key, ("#F1F5F9", "#475569"))
    return f'<span class="chip" style="background:{bg};color:{fg}">{html.escape(str(code))}</span>'


def kpis(items):
    st.markdown("<div class='kpis'>" + "".join(
        f"<div class='kpi'><div class='l'>{html.escape(l)}</div><div class='v'>{v}</div><div class='s'>{html.escape(s or '')}</div></div>"
        for l, v, s in items) + "</div>", unsafe_allow_html=True)


def num(v):
    try:
        x = float(v)
        return None if pd.isna(x) else x
    except (TypeError, ValueError):
        return None


def chart(fig, key=None):
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "responsive": True}, key=key)


# ------------------------------------------------------------------ backend y acceso
def _secrets():
    try:
        return st.secrets if len(st.secrets) else None
    except Exception:
        return None


@st.cache_resource(show_spinner="Conectando…")
def backend():
    return core.crear_backend(secrets=_secrets())


cfg = core.cargar_config()
SEC = _secrets()
PIN = (SEC.get("pin") if SEC else None) or cfg.get("pin")
if PIN and not st.session_state.get("ok"):
    st.markdown("### 🔒 Mi Plan")
    if st.text_input("PIN", type="password") == str(PIN):
        st.session_state.ok = True
        st.rerun()
    st.stop()

BE = backend()
if BE is None:
    st.markdown("### Configura tu Excel")
    st.write("No encontré el Excel del plan. Copia `Plan_Maestro…xlsx` a la carpeta MiPlan o escribe su ruta:")
    ruta = st.text_input("Ruta del Excel", value=cfg.get("excel", ""))
    if st.button("Guardar") and ruta and os.path.exists(ruta):
        cfg["excel"] = ruta
        core.guardar_config(cfg)
        st.cache_resource.clear()
        st.rerun()
    st.stop()

if "v" not in st.session_state:
    st.session_state.v = 0
    if BE.vacio() and getattr(BE, "excel", None):
        from backend import migrar_desde_excel
        migrar_desde_excel(BE, BE.excel)


@st.cache_data(ttl=900, show_spinner="Leyendo el plan…")
def cargar_plan(_be, vp):
    return _be.leer_plan()


@st.cache_data(ttl=90, show_spinner=False)
def cargar_datos(_be, v):
    return _be.dias_df(), _be.actividades_df(), _be.tests_dict()


def refrescar():
    st.session_state.v += 1


def avisar(res, extra=""):
    ok, msg = res
    msg = "" if (msg or "") == extra else (msg or "")
    st.session_state.flash = (ok, " ".join(x for x in (extra, msg) if x))


try:
    PLAN = cargar_plan(BE, st.session_state.get("vp", 0))
except Exception as e:
    st.error(f"No pude leer el plan: {e}")
    st.stop()
DIAS, ACTS, TDICT = cargar_datos(BE, st.session_state.v)
TESTS = tests_objetos(PLAN.tests, TDICT)
ZON = Zonas(calcular_base(TESTS, PLAN.prov))
HOY = dt.date.today()
DF = A.combinar(PLAN.dias, DIAS, ACTS)
W = A.semanal(PLAN.semanas, DF, HOY)
SA = A.semana_actual(W, HOY)
CUR = W[W["semana"] == SA].iloc[0]

# ------------------------------------------------------------------ cabecera
modo = "☁️ nube" if BE.modo == "nube" else "💻 local"
pend = BE.pendientes()
st.markdown(f"<div class='top'><div><div class='t'>Sem {SA} · {esc(CUR['fase'])}</div><div class='s'>{larga(HOY)}</div></div>"
            f"<div><span class='badge'>{modo}</span>"
            + (f"<span class='badge' style='background:#FEF0C7;color:#93370D'>⏳ {len(pend)} por pasar al Excel</span>" if pend else "")
            + "</div></div>", unsafe_allow_html=True)
if "flash" in st.session_state:
    ok, msg = st.session_state.pop("flash")
    (st.success if ok else st.warning)(("✅ " if ok else "⏳ ") + msg)

T_HOY, T_SEM, T_TEST, T_PROG, T_ANA, T_AJ = st.tabs(["📝 Hoy", "📅 Semana", "🧪 Tests", "📈 Progreso", "🖥️ Análisis", "⚙️"])


# ------------------------------------------------------------------ piezas
def tarjeta_plan(r, titulo=None):
    p = []
    if not vacio(r["run_sesion"]) and (r["run_km_plan"] or 0) > 0:
        o = ZON.objetivo(r["tipo_run"])
        p.append(f"<div class='lbl'>🏃 Running · {r['run_km_plan']:g} km {chip(r['tipo_run'])}</div><div class='txt'>{esc(r['run_sesion'])}</div>"
                 + (f"<div class='obj'>🎯 {esc(o)}</div>" if o and o != "—" else ""))
    if not vacio(r["bici_sesion"]):
        mins = f" · {num(r.get('bici_min_plan')):g} min" if num(r.get("bici_min_plan")) else ""
        o = ZON.objetivo(r["tipo_bici"]) if not vacio(r["tipo_bici"]) else ""
        p.append(f"<div class='lbl'>🚴 Bici{mins} {chip(r['tipo_bici'])}</div><div class='txt'>{esc(r['bici_sesion'])}</div>"
                 + (f"<div class='obj'>🎯 {esc(o)}</div>" if o else ""))
    if not vacio(r["nat_sesion"]):
        o = ZON.natacion() if (r["swim_m_plan"] or 0) > 0 else ""
        p.append(f"<div class='lbl'>🏊 Natación · {r['swim_m_plan'] or 0:g} m</div><div class='txt'>{esc(r['nat_sesion'])}</div>"
                 + (f"<div class='obj'>🎯 {esc(o)}</div>" if o else ""))
    for k, lab in (("brick", "🔁 Brick"), ("fuerza_tri", "🏋️ Fuerza triatlón")):
        if not vacio(r.get(k)):
            p.append(f"<div class='lbl'>{lab}</div><div class='txt'>{esc(r[k])}</div>")
    if not vacio(r["gym"]):
        p.append(f"<div class='lbl'>🏋️ Gym / core</div><div class='txt'>{esc(r['gym'])}</div>")
    if not p:
        p.append("<div class='txt muted'>Día de descanso</div>")
    t = titulo or f"Plan · {r['dia']} {dm(r['fecha'])}"
    st.markdown(f"<div class='card'><h4>{t}</h4>{''.join(p)}</div>", unsafe_allow_html=True)


def tarjeta_disposicion(d):
    nivel = d["nivel"]
    titulo = {"Listo": "🟢 Listo para entrenar según el plan", "Precaución": "🟡 Precaución: entrena, pero controla la intensidad",
              "Recupera": "🔴 Prioriza recuperar: cambia la calidad por Z2 suave o descanso",
              "Sin datos": "☀️ Registra tus datos de la mañana para ver tu disposición"}[nivel]
    m = []
    if d["hrv"] is not None:
        base = f" <span style='opacity:.7'>(base {d['hrv_base']:.0f}±{d['hrv_sd']:.0f})</span>" if d["hrv_base"] else ""
        m.append(f"HRV <b>{d['hrv']:.0f}</b> ms{base}")
    if d["rhr"] is not None:
        base = f" <span style='opacity:.7'>(media {d['rhr_base']:.0f})</span>" if d["rhr_base"] else ""
        m.append(f"FC reposo <b>{d['rhr']:.0f}</b>{base}")
    if d["sueno_h"] is not None:
        m.append(f"Sueño <b>{d['sueno_h']:.1f} h</b>" + (f" · {d['score']:.0f} pts" if d["score"] is not None else ""))
    det = "<br>".join("• " + html.escape(a) for a in d["alertas"]) or html.escape(d.get("nota", ""))
    st.markdown(f"<div class='hero h-{nivel.replace(' ', '')}'><div class='n'>{titulo}</div>"
                + (f"<div class='m'>{' · '.join(m)}</div>" if m else "")
                + (f"<div class='d'>{det}</div>" if det else "") + "</div>", unsafe_allow_html=True)


def sugerir_tipo(r, acts_dia):
    hechos = set(acts_dia["tipo"]) if not acts_dia.empty else set()
    if (r["run_km_plan"] or 0) > 0 and "Running" not in hechos:
        return "Running"
    if not vacio(r["bici_sesion"]) and "Bici" not in hechos:
        return "Bici"
    if (r["swim_m_plan"] or 0) > 0 and "Natación" not in hechos:
        return "Natación"
    if not vacio(r["gym"]) and "Gym / fuerza" not in hechos and "descanso" not in str(r["gym"]).lower():
        return "Gym / fuerza"
    return "Running"


# ====================================================================== HOY
with T_HOY:
    fmin, fmax = DF["fecha"].min(), DF["fecha"].max()
    if "fecha" not in st.session_state:
        st.session_state.fecha = min(max(HOY, fmin), fmax)
    with st.container(key="fila_fecha"):
        a, b, c = st.columns([1, 3, 1])
        if a.button("◀", width="stretch", key="dprev"):
            st.session_state.fecha = max(fmin, st.session_state.fecha - dt.timedelta(days=1))
        if c.button("▶", width="stretch", key="dnext"):
            st.session_state.fecha = min(fmax, st.session_state.fecha + dt.timedelta(days=1))
        fecha = b.date_input("Día", value=st.session_state.fecha, min_value=fmin, max_value=fmax, format="DD/MM/YYYY",
                             label_visibility="collapsed")
        st.session_state.fecha = fecha
    r = DF[DF["fecha"] == fecha].iloc[0]
    dia_reg = DIAS[DIAS["fecha"] == fecha].iloc[0].to_dict() if (not DIAS.empty and (DIAS["fecha"] == fecha).any()) else {}
    acts_dia = ACTS[ACTS["fecha"] == fecha].sort_values("hora", na_position="last") if not ACTS.empty else ACTS
    tarjeta_disposicion(A.disposicion(DF, fecha))

    izq, der = st.columns([1, 1.15], gap="large")
    with izq:
        tarjeta_plan(r, f"{'Hoy · ' if fecha == HOY else ''}{r['dia']} {dm(fecha)} · plan")
        carga = r["carga"] if not pd.isna(r["carga"]) else 0
        kpis([("Minutos", f"{(r['duracion'] if not pd.isna(r['duracion']) else 0):.0f}", f"{int(r['n_acts'])} actividades"),
              ("Carga", f"{carga:.0f}", "min × RPE"),
              ("Running", f"{(r['run_km'] if not pd.isna(r['run_km']) else 0):.1f} km", f"plan {r['run_km_plan'] or 0:g} km"),
              ("Estado", (f"{EST_ICON.get(r['estado'], '▫️')} {r['estado']}" if r["estado"] != "Plan"
                          else ("⏳ En curso" if r["n_acts"] else "▫️ Pendiente")),
               "cierra el día al terminar" if r["estado"] == "Plan" and r["n_acts"] else "")])

    with der:
        # ---------------- mañana
        tiene_man = any(not vacio(dia_reg.get(k)) for k in ("hrv", "fc_reposo", "sueno_h", "sleep_score", "sueno"))
        st.markdown("<div class='sec'>☀️ Al despertar</div>", unsafe_allow_html=True)
        with st.expander("Datos de Garmin y sueño" + (" ✓" if tiene_man else ""), expanded=not tiene_man):
            with st.form(f"man_{fecha}"):
                with st.container(key="fila_m1"):
                    a, b = st.columns(2)
                    sh = a.number_input("Sueño (horas)", 0.0, 14.0, step=0.1, value=num(dia_reg.get("sueno_h")), format="%.1f")
                    sc = b.number_input("Puntuación de sueño", 0, 100, step=1,
                                        value=int(num(dia_reg.get("sleep_score"))) if num(dia_reg.get("sleep_score")) is not None else None)
                with st.container(key="fila_m2"):
                    a, b = st.columns(2)
                    hv = a.number_input("HRV noche (ms)", 0, 250, step=1,
                                        value=int(num(dia_reg.get("hrv"))) if num(dia_reg.get("hrv")) is not None else None)
                    rh = b.number_input("FC en reposo", 25, 120, step=1,
                                        value=int(num(dia_reg.get("fc_reposo"))) if num(dia_reg.get("fc_reposo")) is not None else None)
                ss = st.select_slider("¿Cómo dormiste?", ["—", 1, 2, 3, 4, 5],
                                      value=int(num(dia_reg.get("sueno"))) if num(dia_reg.get("sueno")) else "—",
                                      help="1 muy mal · 5 excelente")
                if st.form_submit_button("Guardar mañana", type="primary", width="stretch"):
                    avisar(BE.guardar_dia(fecha, {"sueno_h": sh, "sleep_score": sc, "hrv": hv, "fc_reposo": rh,
                                                  "sueno": None if ss == "—" else ss}), "Datos de la mañana guardados.")
                    refrescar(); st.rerun()

        # ---------------- actividades
        st.markdown("<div class='sec'>🏃 Actividades del día</div>", unsafe_allow_html=True)
        edit_id = st.session_state.get("edit_id")
        for a_ in acts_dia.to_dict("records"):
            with st.container(border=True):
                with st.container(key=f"fila_act_{a_['id']}"):
                    c1, c2, c3 = st.columns([6, 1, 1])
                    hora = f"{a_['hora']} · " if not vacio(a_.get("hora")) else ""
                    cg = carga_act(a_)
                    c1.markdown(f"<div class='act'><div><div class='a'>{ICONO.get(a_['tipo'], '➕')} {hora}{esc(a_['tipo'])}</div>"
                                f"<div class='b'>{esc(resumen_act(a_))}{' · carga ' + format(cg, '.0f') if cg else ''}"
                                f"{'<br>' + esc(a_.get('detalle')) if not vacio(a_.get('detalle')) else ''}</div></div></div>",
                                unsafe_allow_html=True)
                    if c2.button("✏️", key=f"e_{a_['id']}", help="Editar"):
                        st.session_state.edit_id = a_["id"]; st.rerun()
                    if c3.button("🗑️", key=f"d_{a_['id']}", help="Borrar"):
                        avisar(BE.borrar_actividad(a_["id"], fecha), "Actividad borrada.")
                        refrescar(); st.rerun()

        ed = next((x for x in acts_dia.to_dict("records") if x["id"] == edit_id), None) if edit_id else None
        titulo = f"✏️ Editar {ed['tipo']}" if ed else "➕ Agregar actividad"
        with st.expander(titulo, expanded=bool(ed) or acts_dia.empty):
            tipo = ed["tipo"] if ed else st.segmented_control("Tipo", TIPOS, default=sugerir_tipo(r, acts_dia), key=f"tipo_{fecha}")
            tipo = tipo or "Running"
            g = (lambda k: ed.get(k) if ed else None)
            with st.form(f"act_{fecha}_{edit_id or 'nueva'}"):
                with st.container(key="fila_a1"):
                    a, b = st.columns(2)
                    hora = a.text_input("Hora", value=tx(g("hora")) or dt.datetime.now().strftime("%H:%M"))
                    dur = b.number_input("Minutos", 0, 600, step=1, value=int(num(g("duracion"))) if num(g("duracion")) is not None else None)
                dist = ritmo = None
                if tipo in UNIDAD:
                    with st.container(key="fila_a2"):
                        a, b = st.columns(2)
                        u = UNIDAD[tipo]
                        ph = {"Running": r["run_km_plan"], "Bici": r["bici_km_plan"], "Natación": r["swim_m_plan"]}.get(tipo)
                        dist = a.number_input(f"Distancia ({u})", 0.0, 400.0 if u == "km" else 8000.0, step=0.1 if u == "km" else 50.0,
                                              value=num(g("distancia")), placeholder=f"plan {ph:g}" if ph else None)
                        if tipo == "Running":
                            ritmo = b.text_input("Ritmo (m:ss) · vacío = auto", value=tx(g("ritmo")))
                with st.container(key="fila_a3"):
                    a, b = st.columns(2)
                    fc = a.number_input("FC media", 60, 220, step=1, value=int(num(g("fc"))) if num(g("fc")) is not None else None)
                    rpe = b.select_slider("RPE (esfuerzo)", ["—", *range(1, 11)],
                                          value=int(num(g("rpe"))) if num(g("rpe")) is not None else "—",
                                          help="1 muy fácil · 3 conversacional · 5 moderado · 7 duro · 9–10 máximo")
                det_def = tx(g("detalle")) or ("" if ed else (str(r["gym"]) if tipo == "Gym / fuerza" and not vacio(r["gym"]) else ""))
                detalle = st.text_input("Detalle (series, rutina, estructura)", value=det_def)
                notas = st.text_input("Notas", value=tx(g("notas")))
                a, b = st.columns(2)
                guardar = a.form_submit_button("💾 Guardar actividad", type="primary", width="stretch")
                cancelar = b.form_submit_button("Cancelar", width="stretch") if ed else False
            if cancelar:
                st.session_state.pop("edit_id", None); st.rerun()
            if guardar:
                if ritmo and not parse_ok(ritmo):
                    st.error("El ritmo va como 5:05.")
                elif not dur and not dist:
                    st.error("Pon al menos los minutos o la distancia.")
                else:
                    if tipo == "Running" and not ritmo:
                        ritmo = ritmo_auto(dist, dur)
                    act = {"id": ed["id"] if ed else None, "fecha": fecha, "hora": hora.strip(), "tipo": tipo, "duracion": dur,
                           "distancia": dist, "ritmo": ritmo or None, "fc": fc, "rpe": None if rpe == "—" else rpe,
                           "detalle": detalle.strip() or None, "notas": notas.strip() or None}
                    _id, res = BE.guardar_actividad(act)
                    msg = f"{tipo} guardado."
                    if fc and tipo == "Running" and r["tipo_run"] in ("Z2", "FONDO", "RECUPERACION") and fc > ZON.hr["Z2"][1]:
                        msg += f" Ojo: FC {fc} sobre el techo de Z2 ({ZON.hr['Z2'][1]})."
                    avisar(res, msg)
                    st.session_state.pop("edit_id", None)
                    refrescar(); st.rerun()

        # ---------------- cierre
        tiene_cierre = any(not vacio(dia_reg.get(k)) for k in ("fatiga", "dolor", "estado"))
        st.markdown("<div class='sec'>🌙 Cierre del día</div>", unsafe_allow_html=True)
        with st.expander("Estado, fatiga y dolor" + (" ✓" if tiene_cierre else ""), expanded=not tiene_cierre and not acts_dia.empty):
            with st.form(f"cierre_{fecha}"):
                e0 = dia_reg.get("estado") if dia_reg.get("estado") in ESTADOS else ("Hecho" if not acts_dia.empty else "Omitido")
                estado = st.segmented_control("¿Cómo te fue con el plan?", ESTADOS, default=e0)
                with st.container(key="fila_c1"):
                    a, b = st.columns(2)
                    fat = a.select_slider("Fatiga", ["—", 1, 2, 3, 4, 5],
                                          value=int(num(dia_reg.get("fatiga"))) if num(dia_reg.get("fatiga")) else "—", help="1 fresco · 5 muy cansado")
                    dol = b.select_slider("Dolor", ["—", *range(0, 11)],
                                          value=int(num(dia_reg.get("dolor"))) if num(dia_reg.get("dolor")) is not None else "—",
                                          help="0 nada · 4+ revisar")
                notas_d = st.text_area("Notas del día", value=tx(dia_reg.get("notas")), height=70)
                if st.form_submit_button("Cerrar el día", type="primary", width="stretch"):
                    nn = lambda x: None if x == "—" else x
                    avisar(BE.guardar_dia(fecha, {"estado": estado, "fatiga": nn(fat), "dolor": nn(dol),
                                                  "notas": notas_d.strip() or None}), "Día cerrado.")
                    if nn(dol) is not None and nn(dol) >= 4:
                        st.session_state.flash = (False, st.session_state.flash[1] + " Dolor ≥ 4: revisa antes de la próxima calidad.")
                    refrescar(); st.rerun()


# ====================================================================== SEMANA
with T_SEM:
    ops = list(W["semana"])
    lab = {s: f"Sem {s} · {dm(W.loc[W.semana == s, 'inicio'].iloc[0])} – {dm(W.loc[W.semana == s, 'fin'].iloc[0])} · "
              f"{W.loc[W.semana == s, 'fase'].iloc[0]}" for s in ops}
    if "sem" not in st.session_state:
        st.session_state.sem = SA
    with st.container(key="fila_sem"):
        a, b, c = st.columns([1, 4, 1])
        if a.button("◀", width="stretch", key="sprev") and st.session_state.sem > ops[0]:
            st.session_state.sem -= 1
        if c.button("▶", width="stretch", key="snext") and st.session_state.sem < ops[-1]:
            st.session_state.sem += 1
        sem = b.selectbox("Semana", ops, index=ops.index(st.session_state.sem), format_func=lab.get, label_visibility="collapsed")
        st.session_state.sem = sem
    ws = W[W["semana"] == sem].iloc[0]
    st_ = ws["semaforo"] or "—"
    kpis([("Running", f"{ws['run_real']:.0f} / {ws['run_obj']:.0f} km", f"{(ws['run_real'] / ws['run_obj'] * 100 if ws['run_obj'] else 0):.0f} % del plan"),
          ("Bici", f"{ws['bici_real']:.0f} km" if ws["bici_real"] else "—", f"plan {ws['bici_min_plan']:.0f} min" if ws["bici_min_plan"] else ""),
          ("Carga", f"{ws['carga']:.0f}" if ws["carga"] else "—", f"{ws['ratio']:.2f}× vs 4 sem" if pd.notna(ws["ratio"]) else ""),
          ("Recuperación", f"{ws['hrv']:.0f} ms" if pd.notna(ws["hrv"]) else "—",
           f"FC reposo {ws['fc_reposo']:.0f}" if pd.notna(ws["fc_reposo"]) else "HRV media"),
          ("Semáforo", f"<span class='chip sem-{st_.replace(' ', '')}' style='font-size:.85rem;padding:3px 10px;margin:0'>{st_}</span>",
           f"{int(ws['dias_reg'])} días registrados")])
    if not vacio(ws.get("notas")):
        st.caption(f"📌 {ws['notas']}")
    for _, d in DF[DF["semana"] == sem].iterrows():
        km = f"{d['run_km_plan']:g} km {d['tipo_run'] or ''}" if (d["run_km_plan"] or 0) else ("bici/nado/gym" if not vacio(d["bici_sesion"]) or (d["swim_m_plan"] or 0) else "descanso")
        hecho = f" · ✔ {d['run_km']:.1f} km" if not pd.isna(d["run_km"]) and d["run_km"] else ""
        with st.expander(f"{EST_ICON.get(d['estado'], '▫️')} {d['dia']} {dm(d['fecha'])}{' · HOY' if d['fecha'] == HOY else ''} — {km}{hecho}",
                         expanded=d["fecha"] == HOY):
            tarjeta_plan(d, "Plan")
            ad = ACTS[ACTS["fecha"] == d["fecha"]] if not ACTS.empty else ACTS
            if not ad.empty:
                st.markdown("**Registrado:** " + " · ".join(f"{ICONO.get(x['tipo'], '')} {resumen_act(x)}" for x in ad.to_dict("records")))
            if st.button("Registrar este día", key=f"ir_{d['fecha']}"):
                st.session_state.fecha = d["fecha"]
                st.toast("Abre la pestaña 📝 Hoy: ya está en ese día.")
    st.markdown("<div class='sec'>Próximas semanas</div>", unsafe_allow_html=True)
    chart(A.fig_plan_adelante(W, DF, HOY, 10, h=300), "plan_sem")


# ====================================================================== TESTS
with T_TEST:
    trow = PLAN.tests.set_index("key")
    pend_t = sorted([t for t in TESTS if t.estado == "Pendiente" and t.fecha and t.fecha >= HOY], key=lambda t: t.fecha)
    k_next = None
    if pend_t:
        nt = pend_t[0]
        k_next = next(k for k, x in trow.iterrows() if x["fecha"] == nt.fecha and x["test"] == nt.nombre)
        st.markdown(f"<div class='card'><h4>🧪 Próximo: {esc(nt.nombre)} · {nt.deporte} — {larga(nt.fecha)} "
                    f"<span class='badge'>faltan {(nt.fecha - HOY).days} días</span></h4>"
                    f"<div class='lbl'>Qué anotar</div><div class='obj'>{esc(trow.loc[k_next, 'que_anotar'])}</div>"
                    f"<div class='lbl'>Protocolo</div><div class='txt'>{esc(trow.loc[k_next, 'protocolo'])}</div></div>",
                    unsafe_allow_html=True)
    claves = list(trow.index)

    def tlab(k):
        x = trow.loc[k]
        e = (TDICT.get(k) or {}).get("estado") or x["estado"] or "Pendiente"
        ic = {"Completado": "✅", "Reprogramado": "🔁", "Cancelado": "❌"}.get(e, "▫️")
        f = dm(x["fecha"], True) if not vacio(x["fecha"]) else "sin fecha"
        return f"{ic} {f} · {x['deporte']} · {x['test']}"
    sel = st.selectbox("Registrar resultado de", claves, index=claves.index(k_next) if k_next else 0, format_func=tlab)
    tr = trow.loc[sel]
    cur = {c: tr.get(c) for c in TEST_REG_FIELDS}
    cur.update({c: v for c, v in (TDICT.get(sel) or {}).items() if v not in (None, "")})
    gt = lambda c: None if vacio(cur.get(c)) else cur.get(c)
    nombre, dep = str(tr["test"]), tr["deporte"]
    with st.form(f"t_{sel}"):
        st.caption(f"Qué anotar: {tr['que_anotar'] or '—'}")
        estado = st.segmented_control("Estado", ["Completado", "Reprogramado", "Cancelado", "Pendiente"],
                                      default=gt("estado") if gt("estado") in ("Completado", "Reprogramado", "Cancelado") else "Completado")
        dist = tiempo = t200 = pot = None
        with st.container(key="fila_t1"):
            a, b = st.columns(2)
            if dep == "RUN" and "umbral" in nombre.lower():
                dist = a.number_input("Distancia en 30 min (km)", 0.0, 12.0, step=0.01, value=num(gt("distancia")))
            elif dep == "RUN" and any(x in nombre for x in ("5 km", "10 km", "Media")):
                tiempo = a.text_input("Tiempo (17:42 o 1:20:35)", value=tx(gt("tiempo")))
            elif dep == "RUN" and "maratón específico" in nombre:
                tiempo = a.text_input("Ritmo medio bloques (4:05)", value=tx(gt("tiempo")))
            elif dep == "SWIM" and "400" in nombre:
                tiempo = a.text_input("Tiempo 400 m (8:10)", value=tx(gt("tiempo")))
                t200 = b.text_input("Tiempo 200 m (3:50)", value=tx(gt("t200")))
            elif dep == "SWIM":
                tiempo = a.text_input("Tiempo total (38:30)", value=tx(gt("tiempo")))
            elif dep == "BIKE":
                pot = a.number_input("Potencia media (W)", 0, 600, step=1, value=int(num(gt("potencia"))) if num(gt("potencia")) else None)
            fc = b.number_input("FC media", 60, 220, step=1, value=int(num(gt("fc"))) if num(gt("fc")) else None) if not t200 else None
        resultado = st.text_input("Resultado principal (texto)", value=tx(gt("resultado")))
        notas = st.text_area("Notas", value=tx(gt("notas")), height=60)
        ok = st.form_submit_button("💾 Guardar test", type="primary", width="stretch")
    if ok:
        if any(x and parse_time(x) is None for x in (tiempo, t200)):
            st.error("Formato de tiempo: 17:42, 1:20:35 o 4:05.")
        else:
            avisar(BE.guardar_test(sel, {"estado": estado or "Completado", "resultado": resultado.strip() or None, "fc": fc,
                                         "notas": notas.strip() or None, "distancia": dist, "tiempo": (tiempo or "").strip() or None,
                                         "t200": (t200 or "").strip() or None, "potencia": pot}), "Test guardado; zonas recalculadas.")
            refrescar(); st.rerun()
    st.markdown("<div class='sec'>Zonas vigentes</div>", unsafe_allow_html=True)
    b_ = ZON.b
    kpis([("FC umbral", f"{b_.lthr:.0f}", b_.origen["lthr"]), ("Ritmo umbral", f"{mss(b_.umbral)}/km", b_.origen["umbral"]),
          ("Ritmo maratón", f"{mss(b_.rm_actual)}/km", b_.origen["rm"]), ("Objetivo RM", f"{mss(b_.rm_objetivo)}/km", "meta A"),
          ("FC umbral bici", f"{b_.lthr_bici:.0f}", b_.origen["lthr_bici"]),
          ("CSS", f"{mss(b_.css)}/100" if b_.css else "—", b_.origen["css"])])
    st.dataframe(pd.DataFrame([[v[2], A.rango_fc(v[0], v[1]), A.rango_ritmo(ZON.pace[k][0], ZON.pace[k][1])]
                               for k, v in ZON.hr.items()], columns=["Zona", "FC running", "Ritmo /km"]),
                 hide_index=True, width="stretch")


# ====================================================================== PROGRESO (móvil)
with T_PROG:
    hechas = W[W["fin"] < HOY]
    cump = hechas["pct_run"].dropna()
    d7 = DF[(DF["fecha"] > HOY - dt.timedelta(days=7)) & (DF["fecha"] <= HOY)]
    d28 = DF[(DF["fecha"] > HOY - dt.timedelta(days=28)) & (DF["fecha"] <= HOY)]
    kpis([("Km últimos 28 d", f"{d28['run_km'].sum():.0f}", f"plan {d28['run_km_plan'].sum():.0f}"),
          ("Cumplimiento", f"{cump.mean() * 100:.0f} %" if len(cump) else "—", "semanas cerradas"),
          ("HRV 7 d", f"{d7['hrv'].mean():.0f} ms" if d7["hrv"].notna().any() else "—",
           f"28 d: {d28['hrv'].mean():.0f}" if d28["hrv"].notna().any() else ""),
          ("FC reposo 7 d", f"{d7['fc_reposo'].mean():.0f}" if d7["fc_reposo"].notna().any() else "—",
           f"28 d: {d28['fc_reposo'].mean():.0f}" if d28["fc_reposo"].notna().any() else ""),
          ("Sueño 7 d", f"{d7['sueno_h'].mean():.1f} h" if d7["sueno_h"].notna().any() else "—", ""),
          ("Ritmo maratón", mss(ZON.b.rm_actual), ZON.b.origen["rm"])])
    rng = (max(1, SA - 7), min(int(W["semana"].max()), SA + 3))
    st.caption("Banda = tu rango normal de HRV (28 días). Bajo la banda o FC en reposo +5 → prioriza recuperar.")
    chart(A.fig_recuperacion(DF, HOY - dt.timedelta(days=42)), "p_rec")
    chart(A.fig_volumen(W, HOY, "run", rng), "p_vol")
    st.caption("Fitness = carga de 6 semanas · Fatiga = carga de 7 días · Forma verde = fresco, rojo = cargado.")
    chart(A.fig_forma(DF, HOY, TESTS), "p_forma")
    chart(A.fig_sueno(DF, HOY - dt.timedelta(days=28)), "p_sueno")
    chart(A.fig_eficiencia(DF), "p_ef")


# ====================================================================== ANÁLISIS (laptop)
with T_ANA:
    a, b = st.columns([3, 1])
    a.caption("Vista completa para la computadora. El informe HTML queda guardado y se abre en cualquier navegador.")
    if b.button("🧾 Generar informe HTML", type="primary", width="stretch"):
        htmltxt = informe.construir(PLAN, DF, W, TESTS, ZON, HOY)
        st.download_button("⬇️ Descargar informe", htmltxt.encode("utf-8"), file_name=f"informe_{HOY:%Y%m%d}.html", mime="text/html")
        if BE.modo == "local":
            f = core.ROOT / "informes" / f"informe_{HOY:%Y%m%d}.html"
            f.parent.mkdir(exist_ok=True); f.write_text(htmltxt, encoding="utf-8")
            st.success(f"Guardado en {f}")
    st.markdown("<div class='sec'>Carga y forma</div>", unsafe_allow_html=True)
    st.caption("Fitness = carga crónica (42 d) · Fatiga = carga aguda (7 d) · Forma = fitness − fatiga (verde fresco, rojo cargado). "
               "Barras rojas en carga semanal = subida > 30 % vs las 4 semanas previas.")
    chart(A.fig_forma(DF, HOY, TESTS, h=360), "a_forma")
    a, b = st.columns(2)
    with a: chart(A.fig_volumen(W, HOY, "run", (1, min(int(W["semana"].max()), SA + 10))), "a_vol")
    with b: chart(A.fig_carga(W, (1, min(int(W["semana"].max()), SA + 2))), "a_carga")
    st.markdown("<div class='sec'>Recuperación</div>", unsafe_allow_html=True)
    a, b = st.columns(2)
    with a: chart(A.fig_recuperacion(DF), "a_rec")
    with b: chart(A.fig_sueno(DF), "a_sueno")
    a, b = st.columns(2)
    with a: chart(A.fig_carga_vs_hrv(DF), "a_chrv")
    with b: chart(A.fig_minutos_deporte(DF, HOY), "a_min")
    st.markdown("<div class='sec'>Rendimiento</div>", unsafe_allow_html=True)
    a, b, c = st.columns(3)
    with a: chart(A.fig_eficiencia(DF), "a_ef")
    with b: chart(A.fig_ritmo_fc(DF), "a_rfc")
    with c: chart(A.fig_tests(TESTS), "a_tests")
    st.markdown("<div class='sec'>Cumplimiento</div>", unsafe_allow_html=True)
    a, b = st.columns([3, 2])
    with a: chart(A.fig_calendario(DF, HOY, (max(1, SA - 9), SA)), "a_cal")
    with b: chart(A.fig_tipos(DF, HOY), "a_tipos")
    st.markdown("<div class='sec'>Lo que viene</div>", unsafe_allow_html=True)
    chart(A.fig_plan_adelante(W, DF, HOY, 12), "a_plan")
    st.markdown("<div class='sec'>Resumen mensual</div>", unsafe_allow_html=True)
    rm_ = A.resumen_mensual(DF, HOY)
    if rm_.empty:
        st.caption("Aparece con registros.")
    else:
        st.dataframe(rm_, hide_index=True, width="stretch")


# ====================================================================== AJUSTES
with T_AJ:
    if BE.modo == "nube":
        st.markdown("**☁️ Modo nube.** Tus registros se guardan en Google Sheets al instante; no necesitas la compu encendida.")
        st.markdown("Tu Excel se actualiza cuando corres **sincronizar** en tu compu (o al encenderla, si dejaste el acceso directo).")
    else:
        st.markdown(f"**💻 Modo local.** Excel: `{BE.excel}`")
        st.write(f"Pendientes de pasar al Excel: **{len(pend)}**")
        a, b = st.columns(2)
        if a.button("Pasar al Excel ahora", width="stretch"):
            avisar(BE.sincronizar()); refrescar(); st.rerun()
        if b.button("Reescribir todo en el Excel", width="stretch", help="Úsalo si cambiaste a una versión nueva del Excel"):
            BE.marcar_todo(); avisar(BE.sincronizar()); refrescar(); st.rerun()
        st.caption(f"Desde el celular (misma Wi-Fi): http://{core.ip_local()}:8501")
    st.divider()
    if st.button("🔄 Recargar plan y datos"):
        st.session_state.vp = st.session_state.get("vp", 0) + 1
        refrescar(); st.cache_data.clear(); st.rerun()
    st.caption("Las zonas y objetivos usan la misma lógica que la hoja ZONAS_ACTUALES del Excel. "
               "La disposición del día es orientativa: compara tu HRV, FC en reposo y sueño con tu propia línea base.")
