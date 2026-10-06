"""Write the OpenAPI schema to apps/api/openapi.json (the web client's types are generated from it).

    python scripts/export_openapi.py
"""

import json
from pathlib import Path

from app.main import create_app

OUT = Path(__file__).resolve().parents[1] / "openapi.json"
schema = json.dumps(create_app().openapi(), indent=2, sort_keys=True)
OUT.write_text(schema + "\n", encoding="utf-8")
print(f"wrote {OUT}")
