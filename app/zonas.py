"""Motor de zonas: replica la lógica de la hoja ZONAS_ACTUALES del Excel.

La app lo usa para mostrar objetivos de FC/ritmo aunque el Excel no esté recalculado.
Prioridad: Medido > Estimado > Provisional (igual que en el Excel).
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field


def rhalf(x: float) -> int:
    """Redondeo como Excel (0.5 hacia arriba)."""
    return int(math.floor(x + 0.5))


def parse_time(v) -> float | None:
    """Texto '17:42', '1:20:35', '4:05' (o valor que Excel convirtió a hora) -> segundos."""
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        v = v.time()
    if isinstance(v, dt.time):
        secs = v.hour * 3600 + v.minute * 60 + v.second + v.microsecond / 1e6
        return secs / 60 if secs >= 3 * 3600 else secs
    if isinstance(v, (int, float)):
        secs = float(v) * 86400
        return secs / 60 if float(v) * 24 >= 3 else secs
    s = str(v).strip().replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?(:\d+(\.\d+)?){1,2}", s):
        return None
    parts = [float(p) for p in s.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return parts[0] * 60 + parts[1]


def mss(sec: float | None) -> str:
    """Segundos -> 'm:ss' (como TEXT(x,"m:ss") de Excel)."""
    if sec is None:
        return "—"
    s = int(math.floor(sec + 1e-6))   # Excel TEXT() trunca los segundos
    return f"{(s // 60) % 60}:{s % 60:02d}"


def hmmss(sec: float | None) -> str:
    if sec is None:
        return "—"
    s = rhalf(sec)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass
class Test:
    fecha: dt.date | None
    deporte: str
    nombre: str
    estado: str = "Pendiente"
    fc: float | None = None          # col N
    distancia: float | None = None   # col P
    tiempo: object = None            # col Q (texto)
    t200: object = None              # col R (texto)
    potencia: float | None = None    # col S
    orden: int = 0                   # fila en el Excel (desempate)

    @property
    def completado(self) -> bool:
        return self.estado == "Completado"

    @property
    def t_sec(self) -> float | None:
        return parse_time(self.tiempo)

    @property
    def umbral(self) -> float | None:
        """Columna U del Excel: ritmo umbral estimado (s/km), CSS (s/100 m) o FTP (W)."""
        if not self.completado:
            return None
        n, sp, t = self.nombre or "", self.deporte, self.t_sec
        if sp == "RUN" and "Umbral" in n:
            d = _num(self.distancia)
            return 1800.0 / d if d and d > 0 else None
        if sp == "RUN" and "10 km" in n:
            return t / 10 if t else None
        if sp == "RUN" and "5 km" in n:
            return t / 5 * 1.04 if t else None
        if sp == "RUN" and "Media" in n:
            return t / 21.0975 * 0.97 if t else None
        if sp == "SWIM" and "400" in n:
            t2 = parse_time(self.t200)
            return (t - t2) / 2 if (t and t2) else None
        if sp == "BIKE" and "20 min" in n:
            p = _num(self.potencia)
            return float(rhalf(p * 0.95)) if p and p > 0 else None
        return None

    @property
    def rm(self) -> float | None:
        """Columna V del Excel: ritmo maratón estimado (s/km)."""
        if not self.completado or self.deporte != "RUN":
            return None
        n, t = self.nombre or "", self.t_sec
        if not t:
            return None
        if "10 km" in n:
            return t * (42.195 / 10) ** 1.06 / 42.195
        if "5 km" in n:
            return t * (42.195 / 5) ** 1.06 / 42.195
        if "Media" in n:
            return t * 2 ** 1.06 / 42.195
        if "maratón específico" in n:
            return t
        return None


@dataclass
class Provisionales:
    lthr: float = 160
    umbral: str = "3:57"
    rm_actual: str = "4:14"
    rm_objetivo: str = "4:00"
    lthr_bici: float | None = None
    ftp: float | None = None
    css: str | None = None


@dataclass
class Base:
    lthr: float
    umbral: float            # s/km
    rm_actual: float         # s/km
    rm_objetivo: float       # s/km
    lthr_bici: float
    ftp: float | None
    css: float | None        # s/100 m
    umbral_estimado: float | None
    origen: dict = field(default_factory=dict)
    fecha: dict = field(default_factory=dict)


def _latest(tests, pred):
    cands = [t for t in tests if t.completado and t.fecha and pred(t)]
    if not cands:
        return None
    return sorted(cands, key=lambda t: (t.fecha, t.orden))[-1]


def calcular_base(tests: list[Test], prov: Provisionales) -> Base:
    o, f = {}, {}
    run = lambda t: t.deporte == "RUN"
    is_umb = lambda t: "umbral" in (t.nombre or "").lower()

    t = _latest(tests, lambda t: run(t) and is_umb(t) and (_num(t.fc) or 0) > 0)
    lthr = _num(t.fc) if t else float(prov.lthr)
    o["lthr"], f["lthr"] = ("Medido · umbral 30 min", t.fecha) if t else ("Provisional", None)

    tm = _latest(tests, lambda t: run(t) and is_umb(t) and t.umbral)
    te = _latest(tests, lambda t: run(t) and not is_umb(t) and t.umbral)
    est = te.umbral if te else None
    if tm:
        umb, o["umbral"], f["umbral"] = tm.umbral, "Medido · umbral 30 min", tm.fecha
    elif te:
        umb, o["umbral"], f["umbral"] = te.umbral, f"Estimado · {te.nombre}", te.fecha
    else:
        umb, o["umbral"], f["umbral"] = parse_time(prov.umbral), "Provisional", None

    tr = _latest(tests, lambda t: run(t) and t.rm)
    if tr:
        rm = tr.rm
        o["rm"] = "Medido · control RM" if "maratón específico" in tr.nombre else f"Estimado · Riegel ({tr.nombre})"
        f["rm"] = tr.fecha
    else:
        rm, o["rm"], f["rm"] = parse_time(prov.rm_actual), "Provisional", None

    tb = _latest(tests, lambda t: t.deporte == "BIKE" and "20 min" in t.nombre and (_num(t.fc) or 0) > 0)
    if tb:
        lb, o["lthr_bici"], f["lthr_bici"] = float(rhalf(_num(tb.fc) * 0.95)), "Medido · test 20 min", tb.fecha
    elif prov.lthr_bici:
        lb, o["lthr_bici"], f["lthr_bici"] = float(prov.lthr_bici), "Provisional", None
    else:
        lb, o["lthr_bici"], f["lthr_bici"] = lthr - 7, "Provisional (umbral run − 7)", None

    tf = _latest(tests, lambda t: t.deporte == "BIKE" and t.umbral)
    ftp = tf.umbral if tf else (_num(prov.ftp) if prov.ftp not in (None, "") else None)
    o["ftp"] = "Medido · test" if tf else ("Provisional" if ftp else "Sin dato")
    f["ftp"] = tf.fecha if tf else None

    ts = _latest(tests, lambda t: t.deporte == "SWIM" and t.umbral)
    css = ts.umbral if ts else parse_time(prov.css)
    o["css"] = "Medido · test" if ts else ("Provisional" if css else "Sin dato")
    f["css"] = ts.fecha if ts else None

    return Base(lthr, umb, rm, parse_time(prov.rm_objetivo), lb, ftp, css, est, o, f)


HR_ZONES = [("Z1 Recuperación", None, .85), ("Z2 Aeróbico", .85, .90), ("Z3 Ritmo maratón", .90, .95),
            ("Z4 Sub-umbral", .95, 1.00), ("Z5a Umbral", 1.00, 1.03), ("Z5b VO2", 1.03, 1.07), ("Z5c Anaeróbico", 1.07, None)]
PACE_ZONES = [("Z1 Recuperación", 1.29, None), ("Z2 Aeróbico", 1.14, 1.29), ("Z3 Ritmo maratón", 1.06, 1.14),
              ("Z4 Sub-umbral", 1.01, 1.06), ("Z5a Umbral", .97, 1.01), ("Z5b VO2", .90, .97), ("Z5c Anaeróbico", None, .90)]
BIKE_ZONES = [("Z1 Recuperación", None, .81, None, .55), ("Z2 Resistencia", .81, .90, .56, .75),
              ("Z3 Tempo", .90, .94, .76, .90), ("Z4 Umbral", .94, 1.00, .91, 1.05), ("Z5 VO2", 1.00, 1.06, 1.06, 1.20)]


class Zonas:
    def __init__(self, base: Base):
        self.b = base
        L, T, LB = base.lthr, base.umbral, base.lthr_bici
        self.hr = {}
        for name, lo, hi in HR_ZONES:
            k = name.split()[0]
            self.hr[k] = (rhalf(L * lo) if lo else None, rhalf(L * hi) - 1 if hi else None, name)
        self.pace = {}
        for name, lo, hi in PACE_ZONES:
            k = name.split()[0]
            self.pace[k] = (T * lo if lo else None, T * hi if hi else None, name)
        self.bike = {}
        for name, lo, hi, plo, phi in BIKE_ZONES:
            k = name.split()[0]
            w = None
            if base.ftp:
                w = f"{rhalf(base.ftp * plo)}–{rhalf(base.ftp * phi)}" if plo else f"<{rhalf(base.ftp * phi)}"
            self.bike[k] = (rhalf(LB * lo) if lo else None, rhalf(LB * hi) - 1 if hi else None, w, name)

    # helpers con el mismo texto que el Excel
    def fc(self, k): return f"{self.hr[k][0]}–{self.hr[k][1]}"
    def pc(self, k): return f"{mss(self.pace[k][0])}–{mss(self.pace[k][1])}"
    def bfc(self, k): return f"{self.bike[k][0]}–{self.bike[k][1]}"
    def bw(self, k): return "" if not self.b.ftp else f" · {self.bike[k][2]} W"

    def natacion(self) -> str:
        c = self.b.css
        if not c:
            return "Técnica · RPE 3–4 (sin CSS todavía)"
        return f"Técnica RPE 3–4 · series aeróbicas {mss(c + 10)}–{mss(c + 15)}/100 m · umbral ≈ {mss(c)}/100 m"

    def objetivo(self, code: str | None) -> str:
        if not code:
            return ""
        b, RM, RMO, TH = self.b, mss(self.b.rm_actual), mss(self.b.rm_objetivo), mss(self.b.umbral)
        E = lambda k: self.hr[k][1]
        D = lambda k: self.hr[k][0]
        t = {
            "RECUPERACION": f"FC ≤ {E('Z1')} (Z1) · más lento de {mss(self.pace['Z1'][0])}/km",
            "Z2": f"FC {self.fc('Z2')} (Z2) · {self.pc('Z2')}/km",
            "FONDO": f"FC {self.fc('Z2')} (Z2), techo {E('Z2')} · {self.pc('Z2')}/km",
            "FONDO_PROG": f"Fácil: FC {self.fc('Z2')} · {self.pc('Z2')} | Moderado: FC {self.fc('Z3')} · {self.pc('Z3')}/km",
            "RM": f"Fácil: FC {self.fc('Z2')} · {self.pc('Z2')} | Bloques RM: {RM}/km (objetivo {RMO}) · FC ≈ {self.fc('Z3')}",
            "TEMPO": f"Bloques: {self.pc('Z3')}/km · FC {self.fc('Z3')} | resto Z2",
            "UMBRAL": f"Bloques: {TH}–{mss(self.pace['Z4'][1])}/km · FC {D('Z4')}–{E('Z5a')} (sube durante el bloque) | resto Z2",
            "INTERVALOS": f"Reps: {mss(b.umbral * 0.96)}–{mss(b.umbral * 0.98)}/km (ritmo 10K; guíate por ritmo, la FC llega tarde) | recuperación trotando",
            "CUESTAS": f"Subidas por RPE indicado en la sesión (no por ritmo ni FC: la FC llega tarde en tramos cortos) · recuperación bajando suave · resto del rodaje FC {self.fc('Z2')} (Z2)",
            "TEST_AEROBICO": f"Bloque a FC fija {E('Z2') - 5}–{E('Z2')} · anota el ritmo medio en TESTS",
            "TEST_UMBRAL": "30 min máximo y uniforme · anota distancia (P) y FC media últimos 20 min (N) en TESTS",
            "TEST_5K": f"5 km fuerte y uniforme (referencia ≈ {mss(b.umbral / 1.04)}/km) · anota el tiempo en TESTS",
            "TEST_10K": f"10 km uniforme (referencia ≈ {TH}/km) · anota el tiempo en TESTS",
            "TEST_RM": f"2×5 km a {RM}/km · FC ≈ {self.fc('Z3')} · anota ritmo medio de bloques en TESTS",
            "MEDIA_MAR": f"Carrera: ≈ {mss(b.umbral * 1.03)}/km · FC ≈ {self.fc('Z4')} · anota el tiempo en TESTS",
            "CARRERA_MAR": f"Ritmo de la meta elegida ({RMO}/km meta A) · FC ≈ {self.fc('Z3')} · ignora la FC los primeros 5 km",
            "BRICK": f"Post-bici: FC {self.fc('Z2')} · ritmo libre, piernas sueltas",
            "CARRERA_703": f"Primeros 5 km FC ≤ {E('Z2')}; después Z3 ({self.fc('Z3')}) si vas bien",
            "DESCANSO": "—",
            "BICI_Z2": f"FC {self.bfc('Z2')}{self.bw('Z2')}",
            "BICI_FONDO": f"FC {self.bfc('Z2')}{self.bw('Z2')} | final opcional Z3: FC {self.bfc('Z3')}",
            "BICI_TEMPO": f"Bloques FC {self.bfc('Z3')}{self.bw('Z3')} | resto Z2",
            "BICI_TEST": "Según protocolo · anota FC media (N) y potencia (S) en TESTS",
            "BICI_CARRERA": f"FC {self.bfc('Z3')}" + ("" if not b.ftp else f" · 75–83 % FTP: {rhalf(b.ftp * 0.75)}–{rhalf(b.ftp * 0.83)} W"),
        }
        return t.get(code, "")
