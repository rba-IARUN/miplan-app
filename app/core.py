"""Configuración y elección de almacén (nube o local)."""
from __future__ import annotations

import json
import socket
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent                      # carpeta MiPlan (Excel, credenciales, respaldos, informes)
CONFIG = ROOT / "config.json"
CREDS = ROOT / "credenciales.json"


def cargar_config() -> dict:
    cfg = {"excel": "", "sheet_id": "", "pin": ""}
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    if not cfg["excel"] or not Path(cfg["excel"]).exists():
        cands = [c for c in sorted(ROOT.glob("Plan_Maestro*.xlsx")) if not c.name.startswith("~$")]
        if cands:
            cfg["excel"] = str(cands[-1])
    return cfg


def guardar_config(cfg: dict):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def credenciales_nube(secrets=None) -> tuple[dict | None, str | None]:
    """Streamlit Cloud (st.secrets) o archivo credenciales.json + sheet_id en config.json."""
    if secrets is not None:
        try:
            if "gcp_service_account" in secrets and "sheet_id" in secrets:
                return dict(secrets["gcp_service_account"]), str(secrets["sheet_id"])
        except Exception:
            pass
    cfg = cargar_config()
    if CREDS.exists() and cfg.get("sheet_id"):
        return json.loads(CREDS.read_text(encoding="utf-8")), cfg["sheet_id"]
    return None, None


def crear_backend(secrets=None, sheet_factory=None):
    """Devuelve NubeBackend si hay credenciales; si no, LocalBackend con el Excel."""
    from backend import LocalBackend, NubeBackend, abrir_hoja
    import os
    if os.environ.get("MIPLAN_FAKE_SHEET"):          # solo para pruebas automáticas
        import importlib.util
        spec = importlib.util.spec_from_file_location("fake_sheets", os.environ["MIPLAN_FAKE_MODULE"])
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return NubeBackend(mod.FakeSheet(os.environ["MIPLAN_FAKE_SHEET"]))
    creds, sid = credenciales_nube(secrets)
    if creds and sid:
        sh = (sheet_factory or abrir_hoja)(creds, sid)
        return NubeBackend(sh)
    cfg = cargar_config()
    if not cfg.get("excel") or not Path(cfg["excel"]).exists():
        return None
    return LocalBackend(cfg["excel"], ROOT)


def ip_local() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "IP-de-tu-compu"
