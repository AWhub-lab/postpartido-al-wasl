from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    impect_user: str
    impect_pass: str
    impect_base: str = "https://api.impect.com/v5/customerapi"
    timeout: int = 60
    retries: int = 4


def get_settings() -> Settings:
    user = os.environ.get("IMPECT_USER")
    password = os.environ.get("IMPECT_PASS")
    if not user or not password:
        raise RuntimeError("Faltan IMPECT_USER / IMPECT_PASS en el entorno o en .env")
    return Settings(impect_user=user, impect_pass=password)

