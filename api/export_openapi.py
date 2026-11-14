"""Zapisuje api/openapi.json z aplikacji (kontrakt dla frontu i generatorów klienta).

    uv run python -m api.export_openapi          # zapis
    uv run python -m api.export_openapi --check  # exit 1, gdy plik jest nieaktualny
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .main import app

OPENAPI_PATH = Path(__file__).resolve().parent / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        current = OPENAPI_PATH.read_text(encoding="utf-8") if OPENAPI_PATH.exists() else ""
        if current.replace("\r\n", "\n") != content:
            print("api/openapi.json is out of date: run `uv run python -m api.export_openapi`")
            return 1
        return 0
    OPENAPI_PATH.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {OPENAPI_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
