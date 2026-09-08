from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from .config import ROOT


def ensure_crest_path(bundle: dict[str, Any], squad_id: int | None) -> Path | None:
    if squad_id is None:
        return None
    squads = {row.get("id"): row for row in bundle.get("squads", [])}
    squad = squads.get(squad_id) or {}
    image_url = squad.get("imageUrl")
    if not image_url:
        return None
    crests_dir = ROOT / "assets" / "crests"
    crests_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(image_url.split("?")[0]).suffix or ".png"
    crest_path = crests_dir / f"{squad_id}{suffix}"
    if crest_path.exists():
        return crest_path
    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        crest_path.write_bytes(response.content)
        return crest_path
    except requests.RequestException:
        return None
