"""Dónde viven los datos.

- NubeBackend: Google Sheets (la app en Streamlit Cloud y tu compu leen/escriben ahí).
- LocalBackend: SQLite en tu compu + escritura inmediata al Excel (modo sin nube).
Ambos exponen la misma interfaz para la app.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from pathlib import Path

import pandas as pd

from plan_io import Plan, TEST_REG_FIELDS, ExcelBloqueado, escribir_excel, leer_plan, leer_registros_excel, test_key
from registro import ACT_FIELDS, DAY_FIELDS, agregar_dia
from zonas import Provisionales

NUM_DAY = ["sueno", "sueno_h", "sleep_score", "hrv", "fc_reposo", "fatiga", "dolor"]
NUM_ACT = ["duracion", "distancia", "fc", "rpe"]


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def _s(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    return str(v)


def _tipar_dias(df):
    if df.empty:
        return pd.DataFrame(columns=["fecha", *DAY_FIELDS])
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    for k in NUM_DAY:
        df[k] = pd.to_numeric(df[k].replace("", None), errors="coerce")
    for k in ("estado", "notas"):
        df[k] = df[k].replace("", None)
    return df


def _tipar_acts(df):
    if df.empty:
        return pd.DataFrame(columns=ACT_FIELDS)
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    for k in NUM_ACT:
        df[k] = pd.to_numeric(df[k].replace("", None), errors="coerce")
    for k in ("hora", "ritmo", "detalle", "notas"):
        df[k] = df[k].replace("", None)
    return df


def migrar_desde_excel(backend, excel):
    """Primera vez: pasa al almacén lo que ya estuviera registrado en el Excel."""
    dias, tests = leer_registros_excel(excel)
    for r in dias:
        backend.guardar_dia(r["fecha"], {k: r.get(k) for k in DAY_FIELDS}, sync=False)
        if any(r.get(k) not in (None, "") for k in ("run_km", "duracion", "rpe", "bici_km", "swim_m")):
            tipo = "Running" if r.get("run_km") else ("Bici" if r.get("bici_km") else ("Natación" if r.get("swim_m") else "Otro"))
            backend.guardar_actividad({"fecha": r["fecha"], "hora": "", "tipo": tipo, "duracion": r.get("duracion"),
                                       "distancia": r.get("run_km") or r.get("bici_km") or r.get("swim_m"),
                                       "ritmo": r.get("ritmo"), "fc": r.get("fc"), "rpe": r.get("rpe"),
                                       "detalle": "Registro previo (Excel)", "notas": None}, sync=False)
    for t in tests:
        backend.guardar_test(t["key"], t, sync=False)
    return len(dias) + len(tests)


# =====================================================================================
class LocalBackend:
    modo = "local"

    def __init__(self, excel: str, data_dir: Path):
        self.excel = excel
        self.data_dir = Path(data_dir)
        self.db = self.data_dir / "datos" / "registros.db"
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with self._c() as c:
            c.executescript(
                f"CREATE TABLE IF NOT EXISTS dias (fecha TEXT PRIMARY KEY, {', '.join(f'{k} TEXT' for k in DAY_FIELDS)}, actualizado TEXT);"
                f"CREATE TABLE IF NOT EXISTS actividades (id TEXT PRIMARY KEY, {', '.join(f'{k} TEXT' for k in ACT_FIELDS if k != 'id')}, actualizado TEXT);"
                f"CREATE TABLE IF NOT EXISTS tests (key TEXT PRIMARY KEY, {', '.join(f'{k} TEXT' for k in TEST_REG_FIELDS)}, actualizado TEXT);"
                "CREATE TABLE IF NOT EXISTS pendientes (clave TEXT PRIMARY KEY);")

    def _c(self):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        return con

    # ---- plan
    def leer_plan(self) -> Plan:
        return leer_plan(self.excel)

    def vacio(self):
        with self._c() as c:
            return sum(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("dias", "actividades", "tests")) == 0

    # ---- días
    def dias_df(self):
        with self._c() as c:
            return _tipar_dias(pd.read_sql_query("SELECT * FROM dias", c).fillna(""))

    def guardar_dia(self, fecha, campos: dict, sync=True):
        fecha = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)
        with self._c() as c:
            row = c.execute("SELECT * FROM dias WHERE fecha=?", [fecha]).fetchone()
            cur = dict(row) if row else {k: None for k in DAY_FIELDS}
            cur.update({k: _s(v) for k, v in campos.items() if k in DAY_FIELDS})
            c.execute(f"INSERT OR REPLACE INTO dias (fecha, {', '.join(DAY_FIELDS)}, actualizado) VALUES (?{', ?' * len(DAY_FIELDS)}, ?)",
                      [fecha, *[cur.get(k) for k in DAY_FIELDS], _now()])
            c.execute("INSERT OR IGNORE INTO pendientes VALUES (?)", [f"d|{fecha}"])
        return self.sincronizar() if sync else (True, "")

    # ---- actividades
    def actividades_df(self):
        with self._c() as c:
            return _tipar_acts(pd.read_sql_query("SELECT * FROM actividades", c).fillna(""))

    def guardar_actividad(self, a: dict, sync=True):
        a = dict(a)
        a["id"] = a.get("id") or uuid.uuid4().hex[:10]
        fecha = _s(a["fecha"])
        cols = [k for k in ACT_FIELDS]
        with self._c() as c:
            c.execute(f"INSERT OR REPLACE INTO actividades ({', '.join(cols)}, actualizado) VALUES ({', '.join('?' * len(cols))}, ?)",
                      [_s(a.get(k)) for k in cols] + [_now()])
            c.execute("INSERT OR IGNORE INTO pendientes VALUES (?)", [f"d|{fecha}"])
        r = self.sincronizar() if sync else (True, "")
        return a["id"], r

    def borrar_actividad(self, act_id, fecha):
        with self._c() as c:
            c.execute("DELETE FROM actividades WHERE id=?", [act_id])
            c.execute("INSERT OR IGNORE INTO pendientes VALUES (?)", [f"d|{_s(fecha)}"])
        return self.sincronizar()

    # ---- tests
    def tests_dict(self):
        with self._c() as c:
            return {r["key"]: {k: (r[k] or None) for k in TEST_REG_FIELDS} for r in c.execute("SELECT * FROM tests")}

    def guardar_test(self, key, campos, sync=True):
        with self._c() as c:
            c.execute(f"INSERT OR REPLACE INTO tests (key, {', '.join(TEST_REG_FIELDS)}, actualizado) VALUES (?{', ?' * len(TEST_REG_FIELDS)}, ?)",
                      [key, *[_s(campos.get(k)) for k in TEST_REG_FIELDS], _now()])
            c.execute("INSERT OR IGNORE INTO pendientes VALUES (?)", [f"t|{key}"])
        return self.sincronizar() if sync else (True, "")

    # ---- Excel
    def pendientes(self):
        with self._c() as c:
            return [r[0] for r in c.execute("SELECT clave FROM pendientes")]

    def marcar_todo(self):
        with self._c() as c:
            for (f,) in c.execute("SELECT fecha FROM dias UNION SELECT fecha FROM actividades").fetchall():
                c.execute("INSERT OR IGNORE INTO pendientes VALUES (?)", [f"d|{f}"])
            for (k,) in c.execute("SELECT key FROM tests").fetchall():
                c.execute("INSERT OR IGNORE INTO pendientes VALUES (?)", [f"t|{k}"])

    def sincronizar(self):
        pend = self.pendientes()
        if not pend:
            return True, "Excel al día."
        dias, acts, tests = self.dias_df(), self.actividades_df(), self.tests_dict()
        fechas = [dt.date.fromisoformat(p[2:]) for p in pend if p.startswith("d|")]
        filas = []
        for f in fechas:
            dd = dias[dias["fecha"] == f]
            filas.append({"fecha": f, **agregar_dia(dd.iloc[0].to_dict() if len(dd) else None, acts[acts["fecha"] == f])})
        tl = [{"key": p[2:], **tests.get(p[2:], {})} for p in pend if p.startswith("t|")]
        try:
            res = escribir_excel(self.excel, filas, tl, acts_para_excel(acts), self.data_dir / "respaldos")
        except (ExcelBloqueado, PermissionError) as e:
            return False, f"{e if isinstance(e, ExcelBloqueado) else 'Excel en uso.'} Pendientes: {len(pend)}."
        with self._c() as c:
            c.executemany("DELETE FROM pendientes WHERE clave=?", [(p,) for p in pend])
        return True, f"Excel actualizado ({res['dias']} días, {res['tests']} tests)."


def acts_para_excel(acts: pd.DataFrame) -> pd.DataFrame:
    from registro import carga_act
    if acts.empty:
        return acts
    a = acts.copy()
    a["carga"] = [carga_act(r) for r in a.to_dict("records")]
    return a


# =====================================================================================
TABS = {
    "dias": ["fecha", *DAY_FIELDS, "actualizado"],
    "actividades": [*ACT_FIELDS, "actualizado"],
    "tests": ["key", *TEST_REG_FIELDS, "actualizado"],
    "plan_dias": ["fecha", "semana", "dia", "fase", "run_km_plan", "bici_km_plan", "swim_m_plan", "run_sesion", "tipo_run",
                  "bici_sesion", "tipo_bici", "nat_sesion", "gym", "bici_min_plan", "bici_estructura", "brick", "fuerza_tri", "fila"],
    "plan_semanas": ["semana", "inicio", "fin", "fase", "run_obj", "bici_obj", "swim_obj", "notas"],
    "plan_tests": ["key", "fecha", "deporte", "test", "tipo", "protocolo", "datos", "decision", "que_anotar", "fila",
                   "estado", "resultado", "fc", "notas", "distancia", "tiempo", "t200", "potencia"],
    "plan_fondos": ["fecha", "km", "tipo", "descripcion"],
    "plan_config": ["clave", "valor"],
}


def abrir_hoja(creds: dict, sheet_id: str):
    import gspread
    gc = gspread.service_account_from_dict(creds)
    return gc.open_by_key(sheet_id)


class NubeBackend:
    """Google Sheets como almacén. `sh` es un gspread.Spreadsheet (o un doble de pruebas)."""
    modo = "nube"

    def __init__(self, sh):
        self.sh = sh
        self._ws = {}
        existentes = {w.title: w for w in sh.worksheets()}
        for name, hdr in TABS.items():
            ws = existentes.get(name) or sh.add_worksheet(title=name, rows=50, cols=len(hdr))
            vals = ws.row_values(1)
            if vals[:len(hdr)] != hdr:
                if not vals:
                    ws.update(range_name="A1", values=[hdr], value_input_option="RAW")
                else:   # columnas nuevas al final, sin perder datos
                    faltan = [h for h in hdr if h not in vals]
                    if faltan:
                        ws.update(range_name="A1", values=[vals + faltan], value_input_option="RAW")
            self._ws[name] = ws

    # ---- utilidades
    def _tabla(self, name) -> pd.DataFrame:
        vals = self._ws[name].get_all_values()
        if len(vals) <= 1:
            return pd.DataFrame(columns=TABS[name])
        hdr = vals[0]
        rows = [r + [""] * (len(hdr) - len(r)) for r in vals[1:] if any(c != "" for c in r)]
        return pd.DataFrame(rows, columns=hdr)

    def _upsert(self, name, keycol, rec: dict):
        ws = self._ws[name]
        vals = ws.get_all_values()
        hdr = vals[0]
        fila = [_s(rec.get(h)) for h in hdr]
        ki = hdr.index(keycol)
        for i, r in enumerate(vals[1:], start=2):
            if len(r) > ki and r[ki] == fila[ki]:
                ws.update(range_name=f"A{i}", values=[fila], value_input_option="RAW")
                return
        ws.append_row(fila, value_input_option="RAW")

    def _borrar(self, name, keycol, key):
        ws = self._ws[name]
        vals = ws.get_all_values()
        ki = vals[0].index(keycol)
        for i, r in enumerate(vals[1:], start=2):
            if len(r) > ki and r[ki] == key:
                ws.delete_rows(i)
                return

    def escribir_tabla(self, name, df: pd.DataFrame):
        ws = self._ws[name]
        hdr = TABS[name]
        rows = [hdr] + [[_s(r.get(h)) for h in hdr] for r in df.to_dict("records")]
        ws.clear()
        if ws.row_count < len(rows) or ws.col_count < len(hdr):
            ws.resize(rows=max(len(rows), 50), cols=len(hdr))
        ws.update(range_name="A1", values=rows, value_input_option="RAW")

    # ---- plan
    def leer_plan(self) -> Plan:
        d = self._tabla("plan_dias")
        if d.empty:
            raise RuntimeError("La hoja de Google aún no tiene el plan. Corre 'sincronizar' en tu compu una vez.")
        num = lambda s: pd.to_numeric(s.replace("", None), errors="coerce")
        d["fecha"] = pd.to_datetime(d["fecha"]).dt.date
        for k in ("semana", "run_km_plan", "bici_km_plan", "swim_m_plan", "bici_min_plan", "fila"):
            d[k] = num(d[k])
        d["semana"] = d["semana"].astype(int)
        d = d.replace("", None)
        s = self._tabla("plan_semanas")
        for k in ("inicio", "fin"):
            s[k] = pd.to_datetime(s[k]).dt.date
        for k in ("semana", "run_obj", "bici_obj", "swim_obj"):
            s[k] = num(s[k]).fillna(0)
        s["semana"] = s["semana"].astype(int)
        s = s.replace("", None)
        t = self._tabla("plan_tests")
        t["fecha"] = pd.to_datetime(t["fecha"].replace("", None), errors="coerce").dt.date
        t["fecha"] = t["fecha"].where(t["fecha"].notna(), None)
        t["fila"] = num(t["fila"])
        for k in ("fc", "distancia", "potencia"):
            t[k] = num(t[k])
        t = t.replace("", None)
        f = self._tabla("plan_fondos")
        if not f.empty:
            f["fecha"] = pd.to_datetime(f["fecha"]).dt.date
        cfg = dict(self._tabla("plan_config")[["clave", "valor"]].values) if not self._tabla("plan_config").empty else {}
        n = lambda k: float(cfg[k]) if cfg.get(k) not in (None, "") else None
        prov = Provisionales(lthr=n("lthr") or 160, umbral=cfg.get("umbral") or "3:57", rm_actual=cfg.get("rm_actual") or "4:14",
                             rm_objetivo=cfg.get("rm_objetivo") or "4:00", lthr_bici=n("lthr_bici"), ftp=n("ftp"),
                             css=cfg.get("css") or None)
        return Plan(d, s, t, prov, f)

    def publicar_plan(self, plan: Plan):
        self.escribir_tabla("plan_dias", plan.dias)
        self.escribir_tabla("plan_semanas", plan.semanas)
        self.escribir_tabla("plan_tests", plan.tests)
        self.escribir_tabla("plan_fondos", plan.fondos if not plan.fondos.empty else pd.DataFrame(columns=TABS["plan_fondos"]))
        p = plan.prov
        cfg = [("lthr", p.lthr), ("umbral", p.umbral), ("rm_actual", p.rm_actual), ("rm_objetivo", p.rm_objetivo),
               ("lthr_bici", p.lthr_bici), ("ftp", p.ftp), ("css", p.css), ("publicado", _now())]
        self.escribir_tabla("plan_config", pd.DataFrame(cfg, columns=["clave", "valor"]))

    def vacio(self):
        return all(self._tabla(n).empty for n in ("dias", "actividades", "tests"))

    # ---- días / actividades / tests
    def dias_df(self):
        return _tipar_dias(self._tabla("dias"))

    def guardar_dia(self, fecha, campos, sync=True):
        f = _s(fecha)
        cur = self._tabla("dias")
        base = cur[cur["fecha"] == f].iloc[0].to_dict() if (not cur.empty and (cur["fecha"] == f).any()) else {}
        base.update({k: v for k, v in campos.items() if k in DAY_FIELDS})
        base.update({"fecha": f, "actualizado": _now()})
        self._upsert("dias", "fecha", base)
        return True, "Guardado en la nube."

    def actividades_df(self):
        return _tipar_acts(self._tabla("actividades"))

    def guardar_actividad(self, a, sync=True):
        a = dict(a)
        a["id"] = a.get("id") or uuid.uuid4().hex[:10]
        a["actualizado"] = _now()
        self._upsert("actividades", "id", a)
        return a["id"], (True, "Guardado en la nube.")

    def borrar_actividad(self, act_id, fecha):
        self._borrar("actividades", "id", act_id)
        return True, "Actividad borrada."

    def tests_dict(self):
        t = self._tabla("tests")
        return {} if t.empty else {r["key"]: {k: (r.get(k) or None) for k in TEST_REG_FIELDS} for r in t.to_dict("records")}

    def guardar_test(self, key, campos, sync=True):
        self._upsert("tests", "key", {"key": key, **campos, "actualizado": _now()})
        return True, "Guardado en la nube."

    def pendientes(self):
        return []

    def sincronizar(self):
        return True, "Los datos están en Google Sheets; tu Excel se actualiza al correr 'sincronizar' en la compu."
