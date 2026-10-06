"""Write the OpenAPI schema to apps/api/openapi.json (the web client's types are generated from it).

    python scripts/export_openapi.py
"""

import json
from pathlib import Path

from app.main import create_app

OUT = Path(__file__).resolve().parents[1] / "openapi.json"
OUT.write_text(json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {OUT}")
