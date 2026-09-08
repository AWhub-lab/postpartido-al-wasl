from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import ROOT


def bundle_dir(match_id: int) -> Path:
    return ROOT / "data" / "raw" / f"match_{match_id}"


def load_local_bundle(match_id: int) -> dict[str, Any]:
    base = bundle_dir(match_id)
    if not base.exists():
        raise FileNotFoundError(f"No existe bundle local para match_id={match_id}: {base}")
    bundle: dict[str, Any] = {}
    for path in sorted(base.glob("*.json")):
        bundle[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return bundle

