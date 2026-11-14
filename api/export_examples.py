"""Zapisuje przykładowe odpowiedzi do api/examples/ - do mockowania frontu bez uruchamiania backendu.

    uv run python -m api.export_examples
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from .main import API_PREFIX, app

EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"
SITE = "moon_apollo_11"


def main() -> None:
    client = TestClient(app)
    analogs = client.post(f"{API_PREFIX}/analogs", json={"moon": {"site_id": SITE}})
    analogs.raise_for_status()
    responses = {
        "health": client.get(f"{API_PREFIX}/health"),
        "meta": client.get(f"{API_PREFIX}/meta"),
        "moon_sites": client.get(f"{API_PREFIX}/moon/sites"),
        "earth_regions": client.get(f"{API_PREFIX}/earth/regions"),
        "moon_patch": client.get(f"{API_PREFIX}/moon/patch", params={"site_id": SITE}),
        "earth_patch": client.get(f"{API_PREFIX}/earth/patches/{analogs.json()['results'][0]['patch_id']}"),
        "analogs": analogs,
    }
    EXAMPLES_DIR.mkdir(exist_ok=True)
    for name, resp in responses.items():
        resp.raise_for_status()
        path = EXAMPLES_DIR / f"{name}.json"
        path.write_text(json.dumps(resp.json(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
