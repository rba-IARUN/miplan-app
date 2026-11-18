"""Métricas y gráficas (app e informe HTML)."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from registro import agregar_dia, carga_act
from zonas import mss, parse_time

C = {"plan": "#9CA3AF", "run": "#0F766E", "bici": "#C2410C", "swim": "#1D4ED8", "gym": "#7C3AED", "core": "#DB2777",
     "otro": "#6B7280", "carga": "#122B43", "ok": "#15803D", "warn": "#B45309", "bad": "#B91C1C", "grid": "#EEF0F3",
     "text": "#1F2937", "muted": "#6B7280", "hrv": "#0E7490", "rhr": "#BE123C", "sleep": "#4338CA"}
SPORT_COLOR = {"Running": C["run"], "Bici": C["bici"], "Natación": C["swim"], "Gym / fuerza": C["gym"],
               "Core / movilidad": C["core"], "Otro": C["otro"]}
EASY = {"Z2", "FONDO", "RECUPERACION", "FONDO_PROG"}
FONT = "Inter, Segoe UI, Calibri, Arial, sans-serif"


def tema(fig, title=None, h=330, legend=True):
    if title:
        fig.update_layout(title=dict(text=title, x=0.01, y=0.97, font=dict(size=15, color=C["text"], family=FONT)))
    fig.update_layout(
        height=h, margin=dict(l=48, r=24, t=52 if title else 16, b=30), autosize=True,
        plot_bgcolor="white", paper_bgcolor="white", font=dict(family=FONT, size=12, color=C["text"]),
        legend=dict(orientation="h", y=-0.2, yanchor="top", x=0, font=dict(size=11)) if legend else dict(visible=False),
        showlegend=legend, hovermode="x unified", hoverlabel=dict(font_size=12, font_family=FONT),
        bargap=0.25)
    fig.update_xaxes(gridcolor=C["grid"], zeroline=False, automargin=True, linecolor="#D1D5DB", ticks="outside", tickcolor="#D1D5DB")
    fig.update_yaxes(gridcolor=C["grid"], zeroline=False, automargin=True)
    return fig


def vacia(title, msg, h=260):
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper", font=dict(color=C["muted"], size=13))
    fig.update_xaxes(visible=False); fig.update_yaxes(visible=False)
    return tema(fig, title, h, legend=False)


# ======================================================================== datos
def combinar(plan_dias: pd.DataFrame, dias: pd.DataFrame, acts: pd.DataFrame) -> pd.DataFrame:
    df = plan_dias.copy()
    dmap = {r["fecha"]: r for r in dias.to_dict("records")} if not dias.empty else {}
    agr = acts.groupby("fecha") if not acts.empty else None
    filas = []
    for f in df["fecha"]:
        a = agr.get_group(f) if (agr is not None and f in agr.groups) else None
        rec = {k: None for k in ("estado", "run_km", "bici_km", "swim_m", "duracion", "ritmo", "fc", "rpe", "notas")}
        if a is not None or f in dmap:
            rec.update(agregar_dia(dmap.get(f), a))
        mins = {}
        if a is not None:
            for t, g in a.groupby("tipo"):
                mins[t] = pd.to_numeric(g["duracion"], errors="coerce").sum()
        rec.update({f"min_{k}": mins.get(t, 0) for k, t in (("run", "Running"), ("bici", "Bici"), ("swim", "Natación"),
                                                            ("gym", "Gym / fuerza"), ("core", "Core / movilidad"), ("otro", "Otro"))})
        rec["n_acts"] = 0 if a is None else len(a)
        rec["carga"] = None if a is None else sum(x for x in (carga_act(r) for r in a.to_dict("records")) if x is not None) or None
        for k in ("sueno", "sueno_h", "sleep_score", "hrv", "fc_reposo", "fatiga", "dolor"):
            rec[k] = (dmap.get(f) or {}).get(k)
        filas.append(rec)
    agg = pd.DataFrame(filas)
    for c in agg.columns:
        df[c] = agg[c].values
    for k in ("run_km", "bici_km", "swim_m", "duracion", "fc", "rpe", "carga", "sueno", "sueno_h", "sleep_score", "hrv",
              "fc_reposo", "fatiga", "dolor", "run_km_plan", "bici_km_plan", "swim_m_plan", "bici_min_plan"):
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df["estado"] = df["estado"].fillna("Plan").replace("", "Plan")
    df["registrado"] = (df["estado"] != "Plan") | (df["n_acts"] > 0)
    df["pace_s"] = df["ritmo"].map(lambda x: parse_time(x) if isinstance(x, str) else None)
    return df


def semanal(semanas: pd.DataFrame, df: pd.DataFrame, hoy: dt.date) -> pd.DataFrame:
    g = df.groupby("semana")
    w = semanas.copy()
    for col, src in (("run_real", "run_km"), ("bici_real", "bici_km"), ("swim_real", "swim_m"), ("carga", "carga"),
                     ("bici_min_plan", "bici_min_plan"), ("min_total", "duracion")):
        w[col] = w["semana"].map(g[src].sum(min_count=1)).fillna(0)
    for col, src, fn in (("fatiga", "fatiga", "mean"), ("dolor", "dolor", "max"), ("sueno_h", "sueno_h", "mean"),
                         ("hrv", "hrv", "mean"), ("fc_reposo", "fc_reposo", "mean")):
        w[col] = w["semana"].map(getattr(g[src], fn)())
    w["dias_reg"] = w["semana"].map(g["registrado"].sum()).fillna(0).astype(int)
    w["pct_run"] = np.where(w["run_obj"] > 0, w["run_real"] / w["run_obj"], np.nan)
    ratios = []
    for i, row in w.iterrows():
        prev = w.loc[max(0, i - 4):i - 1, "carga"]
        prev = prev[prev > 0]
        ratios.append(row["carga"] / prev.mean() if (row["carga"] > 0 and len(prev)) else np.nan)
    w["ratio"] = ratios
    w["semaforo"] = [semaforo(r, hoy) for _, r in w.iterrows()]
    return w


def semaforo(r, hoy):
    if r["inicio"] > hoy:
        return ""
    if not r["carga"]:
        return "SIN REGISTRO" if r["fin"] < hoy else ""
    dolor = 0 if pd.isna(r["dolor"]) else r["dolor"]
    fat = 0 if pd.isna(r["fatiga"]) else r["fatiga"]
    rat = 0 if pd.isna(r["ratio"]) else r["ratio"]
    pct = 1 if pd.isna(r["pct_run"]) else r["pct_run"]
    if dolor >= 5 or fat >= 4 or rat > 1.3:
        return "ROJO"
    if dolor >= 3 or fat >= 3.5 or rat > 1.2 or (r["fin"] < hoy and pct < 0.8):
        return "AMARILLO"
    return "VERDE"


def semana_actual(semanas, hoy):
    s = semanas[(semanas["inicio"] <= hoy) & (semanas["fin"] >= hoy)]
    if len(s):
        return int(s["semana"].iloc[0])
    return int(semanas["semana"].iloc[0] if hoy < semanas["inicio"].min() else semanas["semana"].iloc[-1])


# ======================================================================== disposición (readiness)
def disposicion(df: pd.DataFrame, fecha: dt.date) -> dict:
    """Orientativo: compara HRV/FC reposo/sueño de hoy con tu propia línea base."""
    d = df.set_index("fecha")
    hoy = d.loc[fecha] if fecha in d.index else None
    prev28 = d[(d.index < fecha) & (d.index >= fecha - dt.timedelta(days=28))]
    prev7 = d[(d.index < fecha) & (d.index >= fecha - dt.timedelta(days=7))]
    out = {"nivel": "Sin datos", "alertas": [], "hrv": None, "hrv_base": None, "hrv_sd": None, "rhr": None,
           "rhr_base": None, "sueno_h": None, "score": None}
    if hoy is None:
        return out
    hrv, rhr, sh, sc = (hoy.get(k) for k in ("hrv", "fc_reposo", "sueno_h", "sleep_score"))
    hb = prev28["hrv"].dropna()
    rb = prev7["fc_reposo"].dropna()
    out.update(hrv=None if pd.isna(hrv) else hrv, rhr=None if pd.isna(rhr) else rhr,
               sueno_h=None if pd.isna(sh) else sh, score=None if pd.isna(sc) else sc)
    datos = 0
    if out["hrv"] is not None:
        datos += 1
        if len(hb) >= 5:
            out["hrv_base"], out["hrv_sd"] = hb.mean(), max(hb.std(ddof=0), 2.0)
            if out["hrv"] < out["hrv_base"] - out["hrv_sd"]:
                out["alertas"].append(f"HRV {out['hrv']:.0f} ms, por debajo de tu rango ({out['hrv_base'] - out['hrv_sd']:.0f}–{out['hrv_base'] + out['hrv_sd']:.0f})")
    if out["rhr"] is not None:
        datos += 1
        if len(rb) >= 3:
            out["rhr_base"] = rb.mean()
            if out["rhr"] >= out["rhr_base"] + 5:
                out["alertas"].append(f"FC en reposo {out['rhr']:.0f}, +{out['rhr'] - out['rhr_base']:.0f} sobre tu media de 7 días")
    if out["sueno_h"] is not None or out["score"] is not None:
        datos += 1
        if (out["sueno_h"] is not None and out["sueno_h"] < 6) or (out["score"] is not None and out["score"] < 60):
            out["alertas"].append("Sueño corto o de baja calidad")
    ayer = d.loc[fecha - dt.timedelta(days=1)] if (fecha - dt.timedelta(days=1)) in d.index else None
    if ayer is not None:
        if not pd.isna(ayer.get("dolor")) and ayer.get("dolor") >= 4:
            out["alertas"].append(f"Dolor {ayer.get('dolor'):.0f}/10 registrado ayer")
        if not pd.isna(ayer.get("fatiga")) and ayer.get("fatiga") >= 4:
            out["alertas"].append(f"Fatiga {ayer.get('fatiga'):.0f}/5 registrada ayer")
    if datos == 0 and not out["alertas"]:
        return out
    n = len(out["alertas"])
    out["nivel"] = "Listo" if n == 0 else ("Precaución" if n == 1 else "Recupera")
    if n == 0 and out["hrv"] is not None and out["hrv_base"] is None:
        out["nota"] = "Construyendo tu línea base de HRV (se necesitan 5 días)."
    return out


# ======================================================================== carga / forma
def carga_diaria(df: pd.DataFrame, hoy: dt.date) -> pd.DataFrame:
    reg = df[df["registrado"]]
    if reg.empty:
        return pd.DataFrame(columns=["fecha", "carga", "atl", "ctl", "tsb"])
    ini = reg["fecha"].min()
    s = df[(df["fecha"] >= ini) & (df["fecha"] <= hoy)][["fecha", "carga"]].copy()
    s["carga"] = s["carga"].fillna(0)
    a7, a42 = 1 - math.exp(-1 / 7), 1 - math.exp(-1 / 42)
    semilla = float(s["carga"].head(14).mean()) if len(s) else 0.0   # evita arrancar desde cero
    atl = ctl = semilla
    A, Cc, T = [], [], []
    for x in s["carga"]:
        T.append(ctl - atl)
        atl += a7 * (x - atl)
        ctl += a42 * (x - ctl)
        A.append(atl); Cc.append(ctl)
    s["atl"], s["ctl"], s["tsb"] = A, Cc, T
    return s


def fig_forma(df, hoy, tests=None, h=340):
    s = carga_diaria(df, hoy)
    if len(s) < 3:
        return vacia("Fitness, fatiga y forma", "Aparece con unos días de registros (minutos × RPE)")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.68, 0.32], vertical_spacing=0.06)
    fig.add_scatter(x=s["fecha"], y=s["ctl"], name="Fitness (42 d)", line=dict(color=C["carga"], width=3), row=1, col=1)
    fig.add_scatter(x=s["fecha"], y=s["atl"], name="Fatiga (7 d)", line=dict(color=C["warn"], width=2, dash="dot"), row=1, col=1)
    pos = s["tsb"].clip(lower=0); neg = s["tsb"].clip(upper=0)
    fig.add_scatter(x=s["fecha"], y=pos, fill="tozeroy", mode="none", fillcolor="rgba(22,163,74,.35)", name="Forma +", row=2, col=1)
    fig.add_scatter(x=s["fecha"], y=neg, fill="tozeroy", mode="none", fillcolor="rgba(220,38,38,.30)", name="Forma −", row=2, col=1)
    for t in tests or []:
        if t.completado and t.fecha and s["fecha"].min() <= t.fecha <= hoy:
            fig.add_vline(x=t.fecha, line=dict(color="#7C3AED", width=1, dash="dot"))
    fig.update_yaxes(title="carga/día", row=1, col=1)
    fig.update_yaxes(title="forma", tickformat=".0f", nticks=4, zeroline=True, zerolinecolor="#9CA3AF", row=2, col=1)
    fig.update_xaxes(tickformat="%d/%m")
    return tema(fig, "Fitness, fatiga y forma", h)


def fig_carga(w, rango=None, h=320):
    d = w if rango is None else w[w["semana"].between(*rango)]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    colors = ["#FCA5A5" if (not pd.isna(r) and r > 1.3) else ("#FDE68A" if (not pd.isna(r) and r > 1.2) else C["carga"]) for r in d["ratio"]]
    fig.add_bar(x=d["semana"], y=d["carga"], name="Carga semanal", marker_color=colors)
    fig.add_scatter(x=d["semana"], y=d["ratio"], name="vs prom. 4 sem.", mode="lines+markers", line=dict(color=C["warn"]),
                    secondary_y=True)
    fig.add_hline(y=1.3, line=dict(color=C["bad"], dash="dot", width=1), secondary_y=True)
    fig.update_yaxes(title="min × RPE", secondary_y=False)
    fig.update_yaxes(title="ratio", range=[0, 2], dtick=0.5, secondary_y=True, showgrid=False)
    fig.update_xaxes(dtick=1 if len(d) <= 16 else 4, title=None)
    return tema(fig, "Carga semanal", h)


def fig_volumen(w, hoy, deporte="run", rango=None, h=320):
    cfg = {"run": ("run_obj", "run_real", "Running (km)", C["run"]), "bici": ("bici_obj", "bici_real", "Bici (km)", C["bici"]),
           "swim": ("swim_obj", "swim_real", "Natación (m)", C["swim"])}[deporte]
    d = w if rango is None else w[w["semana"].between(*rango)]
    sa = semana_actual(w, hoy)
    fig = go.Figure()
    fig.add_bar(x=d["semana"], y=d[cfg[1]], name="Real", marker_color=[cfg[3] if s <= sa else "#E5E7EB" for s in d["semana"]])
    fig.add_scatter(x=d["semana"], y=d[cfg[0]], name="Plan", mode="lines", line=dict(color=C["plan"], dash="dash", width=2))
    if d["semana"].min() <= sa <= d["semana"].max():
        fig.add_vrect(x0=sa - 0.5, x1=sa + 0.5, fillcolor="#FEF3C7", opacity=0.5, line_width=0, layer="below")
    fig.update_xaxes(dtick=1 if len(d) <= 16 else 4, title=None)
    return tema(fig, f"{cfg[2]}: real vs plan", h)


def fig_minutos_deporte(df, hoy, semanas=12, h=320):
    sa = df.loc[df["fecha"] <= hoy, "semana"].max()
    if pd.isna(sa):
        return vacia("Minutos por deporte", "Sin registros todavía")
    d = df[(df["semana"] > sa - semanas) & (df["semana"] <= sa)]
    g = d.groupby("semana")[["min_run", "min_bici", "min_swim", "min_gym", "min_core", "min_otro"]].sum()
    if g.values.sum() == 0:
        return vacia("Minutos por deporte", "Sin actividades registradas todavía")
    fig = go.Figure()
    for col, name in (("min_run", "Running"), ("min_bici", "Bici"), ("min_swim", "Natación"), ("min_gym", "Gym / fuerza"),
                      ("min_core", "Core / movilidad"), ("min_otro", "Otro")):
        if g[col].sum() > 0:
            fig.add_bar(x=g.index, y=g[col] / 60, name=name, marker_color=SPORT_COLOR[name])
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title="horas")
    fig.update_xaxes(dtick=1, title=None)
    return tema(fig, "Horas por deporte", h)


# ======================================================================== recuperación
def fig_recuperacion(df, desde=None, h=330):
    d = df[df["hrv"].notna() | df["fc_reposo"].notna()].sort_values("fecha")
    if desde:
        d = d[d["fecha"] >= desde]
    if len(d) < 2:
        return vacia("HRV y FC en reposo", "Registra HRV y FC en reposo cada mañana (pestaña Hoy → Mañana)")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    hv = d.set_index("fecha")["hrv"]
    base = hv.rolling(28, min_periods=5).mean().shift(1)
    sd = hv.rolling(28, min_periods=5).std(ddof=0).shift(1).clip(lower=2)
    if base.notna().any():
        fig.add_scatter(x=list(base.index) + list(base.index[::-1]), y=list(base + sd) + list((base - sd)[::-1]),
                        fill="toself", fillcolor="rgba(14,116,144,0.10)", line=dict(width=0), name="Tu rango normal HRV",
                        hoverinfo="skip")
    fig.add_scatter(x=hv.index, y=hv, mode="markers", name="HRV noche", marker=dict(color=C["hrv"], size=7, opacity=0.55))
    fig.add_scatter(x=hv.index, y=hv.rolling(7, min_periods=2).mean(), mode="lines", name="HRV media 7 d",
                    line=dict(color=C["hrv"], width=3))
    fig.add_scatter(x=d["fecha"], y=d["fc_reposo"], mode="lines+markers", name="FC reposo", line=dict(color=C["rhr"], width=1.5),
                    marker=dict(size=4), secondary_y=True)
    fig.update_yaxes(title="HRV (ms)", secondary_y=False)
    fig.update_yaxes(title="FC reposo", secondary_y=True, showgrid=False, tickformat=".0f", nticks=5)
    fig.update_yaxes(tickformat=".0f", secondary_y=False)
    fig.update_xaxes(tickformat="%d/%m")
    return tema(fig, "HRV y FC en reposo", h)


def fig_sueno(df, desde=None, h=300):
    d = df[df["sueno_h"].notna()].sort_values("fecha")
    if desde:
        d = d[d["fecha"] >= desde]
    if d.empty:
        return vacia("Sueño", "Registra horas y puntuación de sueño de Garmin cada mañana")
    sc = d["sleep_score"]
    colors = [C["muted"] if pd.isna(x) else ("#15803D" if x >= 80 else ("#65A30D" if x >= 70 else ("#D97706" if x >= 60 else "#DC2626")))
              for x in sc]
    fig = go.Figure()
    fig.add_bar(x=d["fecha"], y=d["sueno_h"], marker_color=colors, name="Horas",
                customdata=sc.fillna(-1), hovertemplate="%{y:.1f} h · puntuación %{customdata}<extra></extra>")
    fig.add_scatter(x=d["fecha"], y=d["sueno_h"].rolling(7, min_periods=2).mean(), name="Media 7 d",
                    line=dict(color=C["sleep"], width=3))
    fig.add_hline(y=7, line=dict(color=C["muted"], dash="dot", width=1))
    fig.update_yaxes(title="horas", range=[0, max(10, d["sueno_h"].max() + 0.5)])
    fig.update_xaxes(tickformat="%d/%m")
    return tema(fig, "Sueño", h)


def fig_carga_vs_hrv(df, h=300):
    d = df.sort_values("fecha").set_index("fecha")
    pares = []
    for f, r in d.iterrows():
        nxt = f + dt.timedelta(days=1)
        if nxt in d.index and not pd.isna(r["carga"]) and not pd.isna(d.loc[nxt, "hrv"]):
            pares.append((r["carga"], d.loc[nxt, "hrv"], f))
    if len(pares) < 8:
        return vacia("Carga de hoy vs HRV de mañana", "Aparece con ~8 días de carga + HRV registrados")
    x, y, f = zip(*pares)
    fig = go.Figure(go.Scatter(x=x, y=y, mode="markers", marker=dict(color=C["hrv"], size=9, opacity=0.6),
                               text=[str(z) for z in f], hovertemplate="%{text}: carga %{x:.0f} → HRV %{y:.0f}<extra></extra>"))
    if len(pares) >= 8:
        m, b = np.polyfit(x, y, 1)
        xs = np.linspace(min(x), max(x), 20)
        fig.add_scatter(x=xs, y=m * xs + b, mode="lines", line=dict(color=C["muted"], dash="dash"), name="Tendencia")
    fig.update_xaxes(title="carga del día (min × RPE)")
    fig.update_yaxes(title="HRV noche siguiente")
    return tema(fig, "Carga vs HRV del día siguiente", h, legend=False)


# ======================================================================== rendimiento
def fig_eficiencia(df, h=300):
    d = df[df["tipo_run"].isin(EASY) & df["pace_s"].notna() & df["fc"].notna() & (df["fc"] > 0)].copy()
    if d.empty:
        return vacia("Eficiencia aeróbica", "Registra ritmo y FC en rodajes fáciles")
    d = d.sort_values("fecha")
    d["ef"] = (1000 / (d["pace_s"] / 60)) / d["fc"]
    fig = go.Figure()
    fig.add_scatter(x=d["fecha"], y=d["ef"], mode="markers", name="Sesión", marker=dict(color=C["run"], size=8, opacity=0.45),
                    customdata=np.stack([d["ritmo"], d["fc"]], axis=1),
                    hovertemplate="%{x|%d/%m}: %{customdata[0]}/km a FC %{customdata[1]}<extra></extra>")
    fig.add_scatter(x=d["fecha"], y=d["ef"].rolling(6, min_periods=2).mean(), mode="lines", name="Tendencia",
                    line=dict(color=C["run"], width=3))
    fig.update_yaxes(title="metros/min por latido (↑ mejor)")
    fig.update_xaxes(tickformat="%d/%m")
    return tema(fig, "Eficiencia aeróbica", h)


def fig_ritmo_fc(df, h=300):
    d = df[df["tipo_run"].isin(EASY) & df["pace_s"].notna() & df["fc"].notna()].copy()
    if len(d) < 3:
        return vacia("Ritmo vs FC", "Aparece con 3+ rodajes fáciles con ritmo y FC")
    d["dias"] = [(f - d["fecha"].min()).days for f in d["fecha"]]
    fig = go.Figure(go.Scatter(x=d["fc"], y=d["pace_s"] / 60, mode="markers",
                               marker=dict(size=10, color=d["dias"], colorscale="Teal", showscale=True,
                                           colorbar=dict(title="días", thickness=10)),
                               text=[f"{f:%d/%m} · {r}/km" for f, r in zip(d["fecha"], d["ritmo"])],
                               hovertemplate="%{text} · FC %{x}<extra></extra>"))
    fig.update_yaxes(title="ritmo (min/km)", autorange="reversed")
    fig.update_xaxes(title="FC media")
    return tema(fig, "Ritmo vs FC", h, legend=False)


def fig_tests(tests, h=300):
    pts = [t for t in tests if t.completado and t.fecha]
    um = [(t.fecha, t.umbral) for t in pts if t.deporte == "RUN" and t.umbral]
    rm = [(t.fecha, t.rm) for t in pts if t.deporte == "RUN" and t.rm]
    hr = [(t.fecha, float(t.fc)) for t in pts if t.deporte == "RUN" and "umbral" in t.nombre.lower() and t.fc]
    if not (um or rm or hr):
        return vacia("Evolución de tests", "Aparece cuando completes tests")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for data, name, col in ((um, "Ritmo umbral", C["run"]), (rm, "Ritmo maratón", C["swim"])):
        if data:
            x, y = zip(*sorted(data))
            fig.add_scatter(x=x, y=[v / 60 for v in y], name=name, mode="lines+markers", line=dict(color=col, width=3),
                            marker=dict(size=9), text=[mss(v) for v in y], hovertemplate="%{x}: %{text}/km<extra>" + name + "</extra>")
    if hr:
        x, y = zip(*sorted(hr))
        fig.add_scatter(x=x, y=y, name="FC umbral", mode="lines+markers", line=dict(color=C["bad"], dash="dot"), secondary_y=True)
    fig.update_yaxes(title="min/km (↑ más rápido)", autorange="reversed", secondary_y=False, tickformat=".2f")
    fig.update_yaxes(title="FC", secondary_y=True, showgrid=False, tickformat=".0f", nticks=4)
    fig.update_xaxes(type="date", tickformat="%d/%m/%y", nticks=6)
    return tema(fig, "Evolución de tests", h)


# ======================================================================== cumplimiento / plan
def fig_calendario(df, hoy, rango=None, h=None):
    d = df if rango is None else df[df["semana"].between(*rango)]
    dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    code = {"Hecho": 3, "Parcial": 2, "Cambiado": 2, "Omitido": 1}
    z, txt = [], []
    sems = sorted(d["semana"].unique())
    for s in sems:
        row, trow = [], []
        for dia in dias:
            x = d[(d["semana"] == s) & (d["dia"] == dia)]
            if x.empty:
                row.append(None); trow.append(""); continue
            x = x.iloc[0]
            plan0 = (x["run_km_plan"] or 0) + (x["bici_km_plan"] or 0) + (x["swim_m_plan"] or 0) == 0
            if x["registrado"]:
                v = code.get(x["estado"], 3)
            elif x["fecha"] > hoy:
                v = None
            else:
                v = -1 if plan0 else 0
            row.append(v)
            trow.append(f"{x['fecha']:%d/%m} · {x['estado']}<br>{str(x['run_sesion'])[:70]}")
        z.append(row); txt.append(trow)
    scale = [[0, "#F3F4F6"], [0.2, "#F3F4F6"], [0.2, "#FCA5A5"], [0.45, "#FCA5A5"], [0.45, "#FDE68A"], [0.7, "#FDE68A"],
             [0.7, "#86EFAC"], [1, "#86EFAC"]]
    fig = go.Figure(go.Heatmap(z=z, x=dias, y=[f"S{s}" for s in sems], text=txt, hoverinfo="text", zmin=-1, zmax=3,
                               colorscale=scale, showscale=False, xgap=4, ygap=4))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, side="top")
    return tema(fig, "Cumplimiento día a día",
                h or max(240, 30 * len(sems) + 90), legend=False)


def fig_tipos(df, hoy, h=None):
    d = df[(df["fecha"] < hoy) & df["tipo_run"].notna() & (df["tipo_run"] != "DESCANSO")]
    if d.empty:
        return vacia("Sesiones por tipo", "Sin sesiones pasadas")
    t = d.groupby("tipo_run").agg(plan=("fecha", "count"), hechas=("registrado", "sum")).sort_values("plan")
    fig = go.Figure()
    fig.add_bar(y=t.index, x=t["plan"], name="Planeadas", orientation="h", marker_color="#E5E7EB")
    fig.add_bar(y=t.index, x=t["hechas"], name="Registradas", orientation="h", marker_color=C["run"])
    fig.update_layout(barmode="overlay")
    return tema(fig, "Sesiones de running por tipo", h or max(240, 26 * len(t) + 100))


def fig_plan_adelante(w, df, hoy, n=12, h=340):
    sa = semana_actual(w, hoy)
    d = w[(w["semana"] >= sa) & (w["semana"] < sa + n)]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    pal = ["#0F766E", "#14B8A6", "#0E7490", "#2563EB", "#7C3AED", "#C2410C", "#B45309", "#4D7C0F"]
    for i, (fase, g) in enumerate(d.groupby("fase", sort=False)):
        fig.add_bar(x=g["semana"], y=g["run_obj"], name=str(fase), marker_color=pal[i % len(pal)], opacity=0.9,
                    hovertemplate="Sem %{x}: %{y} km<extra>" + str(fase) + "</extra>")
    bm = d["semana"].map(df.groupby("semana")["bici_min_plan"].sum(min_count=1))
    if bm.notna().any() and bm.fillna(0).sum() > 0:
        fig.add_scatter(x=d["semana"], y=bm / 60, name="Bici plan (h)", mode="lines+markers", line=dict(color=C["bici"]),
                        secondary_y=True)
    if d["swim_obj"].sum() > 0:
        fig.add_scatter(x=d["semana"], y=d["swim_obj"] / 1000, name="Nado plan (km)", mode="lines+markers",
                        line=dict(color=C["swim"], dash="dot"), secondary_y=True)
    dom = df[(df["dia"] == "Dom") & df["semana"].isin(d["semana"])]
    for _, r in dom.iterrows():
        if (r["run_km_plan"] or 0) >= 24:
            fig.add_annotation(x=r["semana"], y=r["run_km_plan"] or 0, yref="y", text=f"{r['run_km_plan']:g}k",
                               showarrow=False, yshift=-12, font=dict(size=10, color="white"))
    fig.update_yaxes(title="km running", secondary_y=False)
    fig.update_yaxes(title="h bici / km nado", secondary_y=True, showgrid=False)
    fig.update_xaxes(dtick=1, title=None)
    return tema(fig, f"Lo que viene · {n} semanas", h)


def resumen_mensual(df, hoy) -> pd.DataFrame:
    d = df[(df["fecha"] <= hoy) & df["registrado"]].copy()
    if d.empty:
        return pd.DataFrame()
    d["mes"] = [f"{f:%Y-%m}" for f in d["fecha"]]
    p = df[df["fecha"] <= hoy].copy()
    p["mes"] = [f"{f:%Y-%m}" for f in p["fecha"]]
    g = d.groupby("mes").agg(run_km=("run_km", "sum"), bici_km=("bici_km", "sum"), nado_m=("swim_m", "sum"),
                             horas=("duracion", lambda s: s.sum() / 60), carga=("carga", "sum"), dias=("fecha", "count"),
                             hrv=("hrv", "mean"), fc_reposo=("fc_reposo", "mean"), sueno=("sueno_h", "mean"))
    g["run_plan"] = p.groupby("mes")["run_km_plan"].sum()
    g["% run"] = g["run_km"] / g["run_plan"].replace(0, np.nan)
    g = g.reset_index()
    out = pd.DataFrame({"Mes": g["mes"], "Run km": g["run_km"].round(0), "Plan km": g["run_plan"].round(0),
                        "% run": (g["% run"] * 100).round(0), "Bici km": g["bici_km"].round(0), "Nado m": g["nado_m"].round(0),
                        "Horas": g["horas"].round(1), "Carga": g["carga"].round(0), "Días reg.": g["dias"],
                        "HRV": g["hrv"].round(0), "FC reposo": g["fc_reposo"].round(0), "Sueño h": g["sueno"].round(1)})
    return out


def rango_fc(lo, hi):
    if lo is None:
        return f"≤ {hi}"
    if hi is None:
        return f"≥ {lo}"
    return f"{lo}–{hi}"


def rango_ritmo(rapido, lento):
    if rapido is None:
        return f"más rápido de {mss(lento)}"
    if lento is None:
        return f"más lento de {mss(rapido)}"
    return f"{mss(rapido)}–{mss(lento)}"
