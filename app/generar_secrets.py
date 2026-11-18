"""Convierte credenciales.json + sheet_id en el texto que se pega en Streamlit Cloud → Settings → Secrets.

Uso: python generar_secrets.py   (lee ../credenciales.json y ../config.json)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

cfg = core.cargar_config()
if not core.CREDS.exists() or not cfg.get("sheet_id"):
    sys.exit("Falta credenciales.json o sheet_id en config.json")
creds = json.loads(core.CREDS.read_text(encoding="utf-8"))
lineas = [f'sheet_id = "{cfg["sheet_id"]}"']
if cfg.get("pin"):
    lineas.append(f'pin = "{cfg["pin"]}"')
lineas.append("")
lineas.append("[gcp_service_account]")
for k, v in creds.items():
    lineas.append(f"{k} = {json.dumps(v)}")
texto = "\n".join(lineas)
out = core.ROOT / "secrets_para_streamlit.txt"
out.write_text(texto, encoding="utf-8")
print(f"Listo. Copia TODO el contenido de:\n  {out}\ny pégalo en Streamlit Cloud → tu app → Settings → Secrets.\n"
      "No compartas ese archivo con nadie.")
