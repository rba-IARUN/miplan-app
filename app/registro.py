"""Modelo de registro: datos del día (mañana y cierre) + actividades sueltas.

Las actividades del día se suman en una fila del DIARIO del Excel:
km por deporte, minutos totales, RPE ponderado (para que min × RPE = carga real),
FC media ponderada por duración y ritmo de running = minutos / km.
"""
from __future__ import annotations

import math

import pandas as pd

from zonas import mss, parse_time

DAY_FIELDS = ["estado", "sueno", "sueno_h", "sleep_score", "hrv", "fc_reposo", "fatiga", "dolor", "notas"]
ACT_FIELDS = ["id", "fecha", "hora", "tipo", "duracion", "distancia", "ritmo", "fc", "rpe", "detalle", "notas"]
TIPOS = ["Running", "Bici", "Natación", "Gym / fuerza", "Core / movilidad", "Otro"]
ICONO = {"Running": "🏃", "Bici": "🚴", "Natación": "🏊", "Gym / fuerza": "🏋️", "Core / movilidad": "🧘", "Otro": "➕"}
UNIDAD = {"Running": "km", "Bici": "km", "Natación": "m"}
ESTADOS = ["Hecho", "Parcial", "Cambiado", "Omitido"]


def _num(v):
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def ritmo_auto(km, minutos) -> str | None:
    km, minutos = _num(km), _num(minutos)
    if km and minutos and km > 0:
        return mss(minutos * 60 / km)
    return None


def carga_act(a) -> float | None:
    d, r = _num(a.get("duracion")), _num(a.get("rpe"))
    return d * r if (d is not None and r is not None) else None


def _txt(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    v = str(v).strip()
    return v or None


def resumen_act(a) -> str:
    t = a.get("tipo") or "Otro"
    partes = [t.split(" /")[0]]
    dist = _num(a.get("distancia"))
    if dist:
        partes.append(f"{dist:g} {UNIDAD.get(t, '')}".strip())
    if _num(a.get("duracion")):
        partes.append(f"{_num(a.get('duracion')):g}'")
    if _txt(a.get("ritmo")):
        partes.append(f"@{_txt(a.get('ritmo'))}")
    if _num(a.get("fc")):
        partes.append(f"FC {_num(a.get('fc')):g}")
    if _num(a.get("rpe")):
        partes.append(f"RPE {_num(a.get('rpe')):g}")
    return " ".join(partes)


def agregar_dia(dia: dict | None, acts: pd.DataFrame) -> dict:
    """Fila del DIARIO a partir del día y sus actividades."""
    dia = dict(dia or {})
    out = {k: dia.get(k) for k in DAY_FIELDS}
    acts = acts if acts is not None else pd.DataFrame(columns=ACT_FIELDS)
    if not acts.empty:
        recs = acts.to_dict("records")
        run = [a for a in recs if a.get("tipo") == "Running"]
        out["run_km"] = sum(_num(a.get("distancia")) or 0 for a in run) or None
        out["bici_km"] = sum(_num(a.get("distancia")) or 0 for a in recs if a.get("tipo") == "Bici") or None
        out["swim_m"] = sum(_num(a.get("distancia")) or 0 for a in recs if a.get("tipo") == "Natación") or None
        durs = [_num(a.get("duracion")) or 0 for a in recs]
        out["duracion"] = sum(durs) or None
        con_rpe = [(_num(a.get("duracion")) or 0, _num(a.get("rpe"))) for a in recs if _num(a.get("rpe")) is not None]
        dur_rpe = sum(d for d, _ in con_rpe)
        carga = sum(d * r for d, r in con_rpe)
        out["rpe"] = round(carga / dur_rpe, 4) if dur_rpe else None
        # carga del Excel = duración total × RPE; si alguna actividad no tiene RPE, se usa solo lo que sí tiene
        if dur_rpe and out["duracion"] and dur_rpe != out["duracion"]:
            out["rpe"] = round(carga / out["duracion"], 4)
        con_fc = [(_num(a.get("duracion")) or 0, _num(a.get("fc"))) for a in recs if _num(a.get("fc"))]
        w = sum(d for d, _ in con_fc)
        out["fc"] = round(sum(d * f for d, f in con_fc) / w) if w else (con_fc[0][1] if con_fc else None)
        run_min = sum(_num(a.get("duracion")) or 0 for a in run)
        if out["run_km"] and run_min:
            out["ritmo"] = mss(run_min * 60 / out["run_km"])
        elif len(run) == 1 and _txt(run[0].get("ritmo")):
            out["ritmo"] = _txt(run[0].get("ritmo"))
        else:
            out["ritmo"] = None
        if not out.get("estado"):
            out["estado"] = "Hecho"
        resumen = "; ".join(resumen_act(a) for a in sorted(recs, key=lambda a: str(a.get("hora") or "")))
        out["notas"] = " · ".join(x for x in (_txt(dia.get("notas")), resumen) if x)
    else:
        for k in ("run_km", "bici_km", "swim_m", "duracion", "rpe", "fc", "ritmo"):
            out[k] = None
    return out


def parse_ok(ritmo: str | None) -> bool:
    return not ritmo or parse_time(ritmo) is not None
