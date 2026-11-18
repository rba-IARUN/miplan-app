"""Informe HTML autónomo (se abre en cualquier navegador)."""
from __future__ import annotations

import datetime as dt
import html

import pandas as pd

import analisis as A
from zonas import Zonas, mss


def _kpi(label, value, sub="", color="#122B43"):
    return (f'<div class="kpi"><div class="kl">{html.escape(label)}</div><div class="kv" style="color:{color}">{html.escape(str(value))}</div>'
            f'<div class="ks">{html.escape(sub)}</div></div>')


def _fig(f, first):
    return ('<div class="card">' + f.to_html(full_html=False, include_plotlyjs=first, default_width="100%",
                                            default_height=f"{f.layout.height or 330}px",
                                            config={"displaylogo": False, "responsive": True, "displayModeBar": False}) + "</div>")


def construir(plan, df, w, tests, zon: Zonas, hoy: dt.date) -> str:
    sa = A.semana_actual(w, hoy)
    cur = w[w["semana"] == sa].iloc[0]
    d7 = df[(df["fecha"] > hoy - dt.timedelta(days=7)) & (df["fecha"] <= hoy)]
    d28 = df[(df["fecha"] > hoy - dt.timedelta(days=28)) & (df["fecha"] <= hoy)]
    cump = w[w["fin"] < hoy]["pct_run"].dropna()
    prev = w[w["semana"] == sa - 1]["semaforo"].iloc[0] if sa > 1 else "—"
    col = {"VERDE": "#15803D", "AMARILLO": "#B45309", "ROJO": "#B91C1C"}.get(prev, "#122B43")
    disp = A.disposicion(df, hoy)
    kp = "".join([
        _kpi("Semana actual", f"{sa} · {cur['fase']}", f"{cur['inicio']:%d/%m} – {cur['fin']:%d/%m}"),
        _kpi("Running esta semana", f"{cur['run_real']:.0f} / {cur['run_obj']:.0f} km",
             f"{(cur['run_real'] / cur['run_obj'] * 100 if cur['run_obj'] else 0):.0f} % del plan"),
        _kpi("Km últimos 28 días", f"{d28['run_km'].sum():.0f}", f"plan {d28['run_km_plan'].sum():.0f}"),
        _kpi("Cumplimiento medio", f"{cump.mean() * 100:.0f} %" if len(cump) else "—", "semanas cerradas"),
        _kpi("HRV 7 días", f"{d7['hrv'].mean():.0f} ms" if d7["hrv"].notna().any() else "—",
             f"28 d: {d28['hrv'].mean():.0f}" if d28["hrv"].notna().any() else ""),
        _kpi("FC reposo 7 días", f"{d7['fc_reposo'].mean():.0f}" if d7["fc_reposo"].notna().any() else "—", ""),
        _kpi("Semáforo semana anterior", prev or "—", "", col),
        _kpi("Disposición hoy", disp["nivel"], "; ".join(disp["alertas"])[:60]),
    ])
    secciones = [
        ("Carga y forma", [A.fig_forma(df, hoy, tests, h=360)], 1),
        ("", [A.fig_volumen(w, hoy, "run", (1, min(int(w["semana"].max()), sa + 10))), A.fig_carga(w, (1, min(int(w["semana"].max()), sa + 2)))], 2),
        ("Recuperación", [A.fig_recuperacion(df), A.fig_sueno(df), A.fig_carga_vs_hrv(df), A.fig_minutos_deporte(df, hoy)], 2),
        ("Rendimiento", [A.fig_eficiencia(df), A.fig_ritmo_fc(df), A.fig_tests(tests)], 3),
        ("Cumplimiento", [A.fig_calendario(df, hoy, (max(1, sa - 9), sa)), A.fig_tipos(df, hoy)], 2),
        ("Lo que viene", [A.fig_plan_adelante(w, df, hoy, 12)], 1),
    ]
    first = True
    cuerpo = ""
    for titulo, figs, ncol in secciones:
        bloques = ""
        for f in figs:
            bloques += _fig(f, first)
            first = False
        cuerpo += (f"<h2>{titulo}</h2>" if titulo else "") + f'<div class="grid g{ncol}">{bloques}</div>'

    b = zon.b
    zrows = "".join(f"<tr><td>{n}</td><td><b>{v}</b></td><td>{html.escape(o)}</td></tr>" for n, v, o in [
        ("FC umbral running", f"{b.lthr:.0f} lpm", b.origen["lthr"]), ("Ritmo umbral", f"{mss(b.umbral)}/km", b.origen["umbral"]),
        ("Ritmo maratón actual", f"{mss(b.rm_actual)}/km", b.origen["rm"]), ("Ritmo maratón objetivo", f"{mss(b.rm_objetivo)}/km", "Objetivo"),
        ("FC umbral bici", f"{b.lthr_bici:.0f} lpm", b.origen["lthr_bici"]),
        ("FTP bici", f"{b.ftp:.0f} W" if b.ftp else "—", b.origen["ftp"]),
        ("CSS natación", f"{mss(b.css)}/100 m" if b.css else "—", b.origen["css"])])
    hr = "".join(f"<tr><td>{v[2]}</td><td>{A.rango_fc(v[0], v[1])}</td><td>{A.rango_ritmo(zon.pace[k][0], zon.pace[k][1])}</td></tr>"
                 for k, v in zon.hr.items())
    rm_ = A.resumen_mensual(df, hoy)
    mens = rm_.to_html(index=False, na_rep="—", border=0) if not rm_.empty else "<p>Sin registros todavía.</p>"
    t = w[(w["semana"] >= sa - 7) & (w["semana"] <= sa + 2)][
        ["semana", "inicio", "fase", "run_obj", "run_real", "carga", "fatiga", "dolor", "hrv", "fc_reposo", "dias_reg", "semaforo"]].copy()
    t.columns = ["Sem", "Inicio", "Fase", "Run plan", "Run real", "Carga", "Fatiga", "Dolor máx", "HRV", "FC reposo", "Días reg.", "Semáforo"]
    tabla = t.to_html(index=False, na_rep="—", float_format=lambda x: f"{x:.1f}", border=0)

    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Informe de entrenamiento · {hoy:%d/%m/%Y}</title>
<style>
 body{{font-family:Inter,Segoe UI,Calibri,Arial,sans-serif;background:#F4F6F9;color:#1F2937;margin:0}}
 header{{background:linear-gradient(120deg,#122B43,#0F766E);color:#fff;padding:26px 32px}}
 header h1{{margin:0;font-size:24px}} header p{{margin:6px 0 0;opacity:.85}}
 main{{max-width:1320px;margin:0 auto;padding:22px}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:8px}}
 .kpi{{background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 2px rgba(0,0,0,.05)}}
 .kl{{font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:.05em;font-weight:600}}
 .kv{{font-size:22px;font-weight:800;margin-top:4px}} .ks{{font-size:12px;color:#6B7280;margin-top:2px}}
 .grid{{display:grid;gap:16px;margin-bottom:16px}} .g1{{grid-template-columns:1fr}}
 .g2{{grid-template-columns:repeat(2,minmax(0,1fr))}} .g3{{grid-template-columns:repeat(3,minmax(0,1fr))}}
 .card{{background:#fff;border-radius:12px;padding:8px;box-shadow:0 1px 2px rgba(0,0,0,.05);overflow:hidden;min-width:0}}
 h2{{font-size:18px;color:#122B43;margin:28px 0 12px}}
 table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}
 th{{background:#EEF2F7;color:#122B43;text-align:left;padding:8px 10px}} td{{padding:7px 10px;border-top:1px solid #EEF0F3}}
 .tbl{{background:#fff;border-radius:12px;padding:10px;box-shadow:0 1px 2px rgba(0,0,0,.05);overflow-x:auto}}
 footer{{color:#9CA3AF;font-size:12px;text-align:center;padding:26px}}
 @media(max-width:900px){{.g2,.g3{{grid-template-columns:1fr}}}}
</style></head><body>
<header><h1>Informe de entrenamiento · Chicago → CDMX → 70.3</h1>
<p>Generado el {dt.datetime.now():%d/%m/%Y %H:%M} · datos hasta {hoy:%d/%m/%Y}</p></header>
<main><div class="kpis">{kp}</div>{cuerpo}
<h2>Zonas vigentes</h2><div class="grid g2"><div class="tbl"><table><tr><th>Parámetro</th><th>Valor</th><th>Origen</th></tr>{zrows}</table></div>
<div class="tbl"><table><tr><th>Zona</th><th>FC running</th><th>Ritmo /km</th></tr>{hr}</table></div></div>
<h2>Resumen mensual</h2><div class="tbl">{mens}</div>
<h2>Últimas semanas</h2><div class="tbl">{tabla}</div></main>
<footer>“Estimado” y “Provisional” son referencias; prevalece lo medido en tests. La disposición del día es orientativa.</footer>
<script>function aj(){{document.querySelectorAll('.js-plotly-plot').forEach(function(p){{Plotly.Plots.resize(p);}});}}
window.addEventListener('load',function(){{setTimeout(aj,60);}});window.addEventListener('resize',aj);</script>
</body></html>"""
