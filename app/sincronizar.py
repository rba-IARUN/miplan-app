"""Sincroniza tu Excel con la nube (correr en tu compu; ideal al encenderla).

1. Baja de Google Sheets tus días, actividades y tests → los escribe en el Excel (con respaldo).
2. Sube el plan del Excel a Google Sheets (para que la app en la nube vea la versión vigente).
La primera vez, si la hoja está vacía, sube también lo que ya estuviera registrado en el Excel.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
from backend import NubeBackend, acts_para_excel, migrar_desde_excel  # noqa: E402
from plan_io import EXCEL_DIA_COLS, ExcelBloqueado, _d, _valor, escribir_excel, excel_abierto, leer_plan  # noqa: E402
from registro import agregar_dia  # noqa: E402


def filas_excel(nube: NubeBackend) -> tuple[list[dict], pd.DataFrame, list[dict]]:
    dias, acts = nube.dias_df(), nube.actividades_df()
    fechas = sorted(set(dias["fecha"]).union(set(acts["fecha"])) - {None})
    filas = []
    for f in fechas:
        dd = dias[dias["fecha"] == f]
        filas.append({"fecha": f, **agregar_dia(dd.iloc[0].to_dict() if len(dd) else None, acts[acts["fecha"] == f])})
    tests = [{"key": k, **v} for k, v in nube.tests_dict().items()]
    return filas, acts_para_excel(acts), tests


def hay_cambios(excel, filas, tests_n) -> bool:
    wb = openpyxl.load_workbook(excel, data_only=False)
    d = wb["DIARIO"]
    idx = {_d(d[f"A{r}"].value): r for r in range(2, d.max_row + 1)}
    for reg in filas:
        r = idx.get(reg["fecha"])
        if not r:
            continue
        for campo, col in EXCEL_DIA_COLS.items():
            a = _valor(campo, reg.get(campo))
            if campo == "estado" and a is None:
                a = "Plan"
            b = d[f"{col}{r}"].value
            if (a or None) != (b or None) and str(a) != str(b):
                return True
    n_act = (wb["ACTIVIDADES"].max_row - 1) if "ACTIVIDADES" in wb.sheetnames else -1
    wb.close()
    return n_act != tests_n


def main(sheet_factory=None, excel=None) -> int:
    cfg = core.cargar_config()
    excel = excel or cfg.get("excel")
    if not excel or not Path(excel).exists():
        print("❌ No encuentro el Excel. Revisa 'excel' en config.json.")
        return 1
    be = core.crear_backend(sheet_factory=sheet_factory)
    if not isinstance(be, NubeBackend):
        print("❌ Falta configurar la nube (credenciales.json y sheet_id en config.json). Ver GUIA.md.")
        return 1
    if excel_abierto(Path(excel)):
        print("⏳ El Excel está abierto. Ciérralo y vuelve a correr la sincronización.")
        return 2
    if be.vacio():
        n = migrar_desde_excel(be, excel)
        if n:
            print(f"↑ Subí a la nube {n} registros que ya estaban en el Excel.")
    filas, acts, tests = filas_excel(be)
    import hashlib, json
    huella = hashlib.sha1(json.dumps([filas, acts.astype(str).to_dict("records"), tests], default=str, sort_keys=True).encode()).hexdigest()
    marca = core.ROOT / "datos" / "ultima_sincronizacion.txt"
    marca.parent.mkdir(exist_ok=True)
    previa = marca.read_text().strip() if marca.exists() else ""
    if (huella != previa and (filas or len(acts) or tests)) or hay_cambios(excel, filas, len(acts)):
        try:
            res = escribir_excel(excel, filas, tests, acts, core.ROOT / "respaldos")
            print(f"↓ Excel actualizado: {res['dias']} días, {res['actividades']} actividades, {res['tests']} tests. "
                  f"Respaldo: {Path(res['respaldo']).name}")
            marca.write_text(huella)
        except ExcelBloqueado as e:
            print(f"⏳ {e}")
            return 2
    else:
        print("↓ Excel ya estaba al día.")
    be.publicar_plan(leer_plan(excel))
    print(f"↑ Plan publicado en la nube ({dt.datetime.now():%d/%m %H:%M}).")
    return 0


if __name__ == "__main__":
    code = main()
    sys.exit(code)
