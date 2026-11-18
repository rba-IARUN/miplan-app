"""Excel del plan: lectura del plan y escritura segura de registros.

Solo se escriben columnas de REGISTRO del DIARIO (Q:X, Z:AC y AQ:AT), las de resultado en
TESTS_CALENDARIO (L:S) y la hoja ACTIVIDADES (detalle de cada actividad). Nunca el plan ni fórmulas.
Antes de escribir se guarda un respaldo. Si el Excel está abierto, no se escribe.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from zonas import Provisionales

PLAN_COLS = {
    "fecha": "A", "semana": "B", "dia": "C", "fase": "D", "run_km_plan": "E", "bici_km_plan": "F", "swim_m_plan": "G",
    "run_sesion": "H", "tipo_run": "I", "bici_sesion": "K", "tipo_bici": "L", "nat_sesion": "N", "gym": "P",
    "bici_min_plan": "AM", "bici_estructura": "AN", "brick": "AO", "fuerza_tri": "AP",
}
# campos del día que van al Excel (agregados desde las actividades + datos de mañana/cierre)
EXCEL_DIA_COLS = {
    "estado": "Q", "run_km": "R", "bici_km": "S", "swim_m": "T", "duracion": "U", "ritmo": "V", "fc": "W", "rpe": "X",
    "sueno": "Z", "fatiga": "AA", "dolor": "AB", "notas": "AC",
    "sueno_h": "AQ", "sleep_score": "AR", "hrv": "AS", "fc_reposo": "AT",
}
GARMIN_HDR = {"AQ": "Sueño Garmin (h)", "AR": "Puntuación sueño", "AS": "HRV noche (ms)", "AT": "FC reposo (lpm)"}
TEST_COLS = {"fecha": "A", "deporte": "B", "test": "C", "tipo": "D", "protocolo": "H", "datos": "I", "decision": "J",
             "estado": "L", "resultado": "M", "fc": "N", "notas": "O", "distancia": "P", "tiempo": "Q", "t200": "R",
             "potencia": "S", "que_anotar": "W"}
TEST_REG_FIELDS = ["estado", "resultado", "fc", "notas", "distancia", "tiempo", "t200", "potencia"]
ACT_COLS = ["fecha", "hora", "tipo", "duracion", "distancia", "ritmo", "fc", "rpe", "carga", "detalle", "notas", "id"]
ACT_HDR = ["Fecha", "Hora", "Actividad", "Minutos", "Distancia (km o m)", "Ritmo", "FC media", "RPE", "Carga (min×RPE)",
           "Detalle", "Notas", "ID"]
TEXT_FIELDS = {"ritmo", "tiempo", "t200", "resultado", "notas", "detalle", "hora"}


class ExcelBloqueado(Exception):
    pass


def _d(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.strip()):
        return dt.date.fromisoformat(v.strip())
    return None


def test_key(fecha, deporte, nombre) -> str:
    return f"{fecha.isoformat() if fecha else 'sin-fecha'}|{deporte}|{nombre}"


@dataclass
class Plan:
    dias: pd.DataFrame
    semanas: pd.DataFrame
    tests: pd.DataFrame
    prov: Provisionales
    fondos: pd.DataFrame


# ------------------------------------------------------------------ lectura
def leer_plan(path) -> Plan:
    wb = openpyxl.load_workbook(path, data_only=True)
    d = wb["DIARIO"]
    rows = []
    for r in range(2, d.max_row + 1):
        f = _d(d[f"A{r}"].value)
        if f:
            rec = {k: d[f"{c}{r}"].value for k, c in PLAN_COLS.items()}
            rec["fecha"], rec["fila"] = f, r
            rows.append(rec)
    s = wb["SEMANAS"]
    sem = [{"semana": int(s[f"A{r}"].value), "inicio": _d(s[f"B{r}"].value), "fin": _d(s[f"C{r}"].value),
            "fase": s[f"D{r}"].value, "run_obj": s[f"E{r}"].value or 0, "bici_obj": s[f"F{r}"].value or 0,
            "swim_obj": s[f"G{r}"].value or 0, "notas": s[f"X{r}"].value}
           for r in range(2, s.max_row + 1) if s[f"A{r}"].value is not None]
    t = wb["TESTS_CALENDARIO"]
    tl = []
    for r in range(2, t.max_row + 1):
        if t[f"C{r}"].value:
            rec = {k: t[f"{c}{r}"].value for k, c in TEST_COLS.items()}
            rec["fecha"] = _d(rec["fecha"])
            rec["fila"] = r
            rec["key"] = test_key(rec["fecha"], rec["deporte"], rec["test"])
            tl.append(rec)
    z = wb["ZONAS_ACTUALES"]
    prov = Provisionales(lthr=z["F6"].value or 160, umbral=z["F7"].value or "3:57", rm_actual=z["F8"].value or "4:14",
                         rm_objetivo=z["F9"].value or "4:00", lthr_bici=z["F10"].value, ftp=z["F11"].value, css=z["F12"].value)
    fondos = pd.DataFrame()
    if "V10_FONDOS_OFICIAL" in wb.sheetnames:
        fo = wb["V10_FONDOS_OFICIAL"]
        fondos = pd.DataFrame([{"fecha": _d(fo[f"A{r}"].value), "km": fo[f"B{r}"].value, "tipo": fo[f"C{r}"].value,
                                "descripcion": fo[f"D{r}"].value} for r in range(2, fo.max_row + 1) if fo[f"A{r}"].value])
    wb.close()
    return Plan(pd.DataFrame(rows), pd.DataFrame(sem), pd.DataFrame(tl), prov, fondos)


def leer_registros_excel(path) -> tuple[list[dict], list[dict]]:
    """Días y tests ya registrados en el Excel (para migrarlos la primera vez)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    d, t = wb["DIARIO"], wb["TESTS_CALENDARIO"]
    dias = []
    for r in range(2, d.max_row + 1):
        f = _d(d[f"A{r}"].value)
        if not f:
            continue
        rec = {k: d[f"{c}{r}"].value for k, c in EXCEL_DIA_COLS.items()}
        if (rec.get("estado") or "Plan") != "Plan" or any(rec.get(k) not in (None, "") for k in ("run_km", "duracion", "rpe", "hrv")):
            rec["fecha"] = f
            dias.append(rec)
    tests = []
    for r in range(2, t.max_row + 1):
        if t[f"C{r}"].value and (t[f"L{r}"].value or "Pendiente") != "Pendiente":
            rec = {k: t[f"{TEST_COLS[k]}{r}"].value for k in TEST_REG_FIELDS}
            rec["key"] = test_key(_d(t[f"A{r}"].value), t[f"B{r}"].value, t[f"C{r}"].value)
            tests.append(rec)
    wb.close()
    return dias, tests


# ------------------------------------------------------------------ escritura
def excel_abierto(path: Path) -> bool:
    path = Path(path)
    if (path.parent / f"~${path.name}").exists():
        return True
    try:
        with open(path, "r+b"):
            return False
    except PermissionError:
        return True


def respaldar(path: Path, carpeta: Path, conservar: int = 30) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{path.stem}_{dt.datetime.now():%Y%m%d_%H%M%S}{path.suffix}"
    shutil.copy2(path, destino)
    for f in sorted(carpeta.glob(f"{path.stem}_*{path.suffix}"))[:-conservar]:
        f.unlink(missing_ok=True)
    return destino


def _post_guardado(path: Path):
    """Marca formatos numéricos y fuerza recálculo completo al abrir en Excel."""
    tmp = path.with_name(path.stem + ".tmp.xlsx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/styles.xml":
                s = data.decode("utf-8")
                s = re.sub(r"<xf [^>]*numFmtId=\"\d+\"[^>]*>",
                           lambda m: m.group(0) if ('numFmtId="0"' in m.group(0) or "applyNumberFormat" in m.group(0))
                           else m.group(0).replace("<xf ", '<xf applyNumberFormat="1" ', 1), s)
                data = s.encode("utf-8")
            elif item.filename == "xl/workbook.xml":
                s = data.decode("utf-8")
                if "fullCalcOnLoad" not in s:
                    s = re.sub(r"<calcPr", '<calcPr fullCalcOnLoad="1"', s, count=1) if "<calcPr" in s \
                        else s.replace("</workbook>", '<calcPr fullCalcOnLoad="1"/></workbook>')
                data = s.encode("utf-8")
            zout.writestr(item, data)
    os.replace(tmp, path)


def _valor(campo, v):
    if v is None or v == "" or (isinstance(v, float) and pd.isna(v)):
        return None
    if campo in TEXT_FIELDS or campo == "estado":
        return str(v)
    try:
        x = float(v)
        return int(x) if x.is_integer() else round(x, 4)
    except (TypeError, ValueError):
        return v


NAVY, TEAL, CREAM, GRID = "122B43", "0B5E57", "FFF7DB", "D9DEE5"
_thin = Side(style="thin", color=GRID)
_box = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)


def asegurar_estructura(wb) -> bool:
    """Columnas Garmin (AQ:AT) en DIARIO y hoja ACTIVIDADES. Devuelve True si cambió algo."""
    cambio = False
    d = wb["DIARIO"]
    for col, h in GARMIN_HDR.items():
        if d[f"{col}1"].value != h:
            d[f"{col}1"].value = h
            c = d[f"{col}1"]
            c.font = Font(name="Calibri", sz=10, b=True, color="FFFFFF"); c.fill = PatternFill("solid", start_color=TEAL)
            c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center"); c.border = _box
            d.column_dimensions[col].width = 10
            for r in range(2, d.max_row + 1):
                x = d[f"{col}{r}"]
                x.fill = PatternFill("solid", start_color=CREAM); x.border = _box
                x.alignment = Alignment(horizontal="center", vertical="top"); x.font = Font(name="Calibri", sz=10)
            cambio = True
    if "ACTIVIDADES" not in wb.sheetnames:
        a = wb.create_sheet("ACTIVIDADES", index=wb.sheetnames.index("TESTS_CALENDARIO") + 1)
        for i, h in enumerate(ACT_HDR, start=1):
            c = a.cell(1, i, h)
            c.font = Font(name="Calibri", sz=10, b=True, color="FFFFFF"); c.fill = PatternFill("solid", start_color=TEAL)
            c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center"); c.border = _box
        for col, w in zip("ABCDEFGHIJKL", (11, 7, 12, 9, 12, 9, 9, 7, 10, 40, 40, 10)):
            a.column_dimensions[col].width = w
        a.freeze_panes = "A2"
        a.sheet_properties.tabColor = "1E6B34"
        a.row_dimensions[1].height = 30
        cambio = True
    return cambio


def _escribir_actividades(wb, acts: pd.DataFrame):
    a = wb["ACTIVIDADES"]
    if a.max_row > 1:
        a.delete_rows(2, a.max_row - 1)
    if acts is None or acts.empty:
        return
    acts = acts.sort_values(["fecha", "hora"], na_position="last")
    for i, (_, r) in enumerate(acts.iterrows(), start=2):
        for j, k in enumerate(ACT_COLS, start=1):
            v = r.get(k)
            if k == "fecha":
                v = dt.datetime.combine(_d(v) or v, dt.time())
            c = a.cell(i, j, _valor(k, v) if k != "fecha" else v)
            c.font = Font(name="Calibri", sz=10); c.border = _box
            c.alignment = Alignment(vertical="top", wrap_text=k in ("detalle", "notas"),
                                    horizontal="left" if k in ("detalle", "notas", "tipo") else "center")
            if k == "fecha":
                c.number_format = "yyyy-mm-dd"
            if k in ("ritmo", "hora"):
                c.number_format = "@"


def escribir_excel(path, dias: list[dict], tests: list[dict], actividades: pd.DataFrame | None,
                   carpeta_respaldos: Path) -> dict:
    path = Path(path)
    if excel_abierto(path):
        raise ExcelBloqueado("El Excel está abierto. Ciérralo para pasar los registros.")
    respaldo = respaldar(path, carpeta_respaldos)
    wb = openpyxl.load_workbook(path)
    asegurar_estructura(wb)
    d, t = wb["DIARIO"], wb["TESTS_CALENDARIO"]
    filas = {_d(d[f"A{r}"].value): r for r in range(2, d.max_row + 1) if _d(d[f"A{r}"].value)}
    n_d = 0
    for reg in dias:
        r = filas.get(_d(reg["fecha"]))
        if not r:
            continue
        for campo, col in EXCEL_DIA_COLS.items():
            c = d[f"{col}{r}"]
            c.value = _valor(campo, reg.get(campo))
            if campo == "estado" and c.value is None:
                c.value = "Plan"
            if campo == "ritmo":
                c.number_format = "@"
        n_d += 1
    tf = {test_key(_d(t[f"A{r}"].value), t[f"B{r}"].value, t[f"C{r}"].value): r for r in range(2, t.max_row + 1) if t[f"C{r}"].value}
    n_t = 0
    for te in tests:
        r = tf.get(te["key"])
        if not r:
            continue
        for campo in TEST_REG_FIELDS:
            c = t[f"{TEST_COLS[campo]}{r}"]
            c.value = _valor(campo, te.get(campo))
            if campo in ("tiempo", "t200"):
                c.number_format = "@"
        n_t += 1
    if actividades is not None:
        _escribir_actividades(wb, actividades)
    wb.save(path)
    _post_guardado(path)
    return {"dias": n_d, "tests": n_t, "actividades": 0 if actividades is None else len(actividades), "respaldo": str(respaldo)}


def preparar_excel(path_in, path_out):
    """Crea la versión con columnas Garmin y hoja ACTIVIDADES (sin tocar nada más)."""
    wb = openpyxl.load_workbook(path_in)
    asegurar_estructura(wb)
    wb.save(path_out)
    _post_guardado(Path(path_out))


def tests_objetos(tests_df: pd.DataFrame, overrides: dict) -> list:
    """Tests del plan con los resultados registrados encima (para el motor de zonas)."""
    from zonas import Test
    out = []
    for r in tests_df.to_dict("records"):
        rec = dict(r)
        rec.update({k: v for k, v in (overrides.get(r["key"]) or {}).items() if k in TEST_REG_FIELDS and v not in (None, "")})
        f = rec.get("fecha")
        f = None if (f is None or (isinstance(f, float) and pd.isna(f))) else f
        out.append(Test(fecha=f, deporte=rec["deporte"], nombre=rec["test"], estado=rec.get("estado") or "Pendiente",
                        fc=rec.get("fc"), distancia=rec.get("distancia"), tiempo=rec.get("tiempo"), t200=rec.get("t200"),
                        potencia=rec.get("potencia"), orden=int(rec.get("fila") or 0)))
    return out
