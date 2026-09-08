from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import impectPy
import json
import requests
from impectPy.helpers import HTTPError

from .config import Settings


class ImpectClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.token = self._login()

    def _login(self) -> str:
        try:
            return impectPy.getAccessToken(self.settings.impect_user, self.settings.impect_pass)
        except HTTPError as exc:
            message = str(exc)
            if "401" in message or "Invalid User Credentials" in message:
                raise RuntimeError(
                    "IMPECT devolvio 401 al iniciar sesion. Revisa IMPECT_USER e IMPECT_PASS en .env. "
                    "Si ya teneis unas credenciales funcionando en otro proyecto, copia exactamente esas."
                ) from exc
            raise RuntimeError(f"No se pudo iniciar sesion en IMPECT: {message}") from exc

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.settings.impect_base}{path}"
        last_error: Exception | None = None
        for attempt in range(self.settings.retries):
            response = self.session.get(url, headers=self._headers(), params=params or {}, timeout=self.settings.timeout)
            if response.status_code == 401:
                self.token = self._login()
                continue
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", max(2, 2**attempt)))
                time.sleep(wait)
                continue
            try:
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if response.status_code >= 500 and attempt + 1 < self.settings.retries:
                    time.sleep(max(2, 2**attempt))
                    continue
                raise
        raise RuntimeError(f"No se pudo completar {path}") from last_error

    def get_matches(self, iteration_id: int) -> list[dict[str, Any]]:
        return self._get(f"/iterations/{iteration_id}/matches").get("data", [])

    def get_iterations(self) -> list[dict[str, Any]]:
        return self._get("/iterations").get("data", [])

    def get_squads(self, iteration_id: int) -> list[dict[str, Any]]:
        return self._get(f"/iterations/{iteration_id}/squads").get("data", [])

    def get_iteration_players(self, iteration_id: int) -> list[dict[str, Any]]:
        return self._get(f"/iterations/{iteration_id}/players").get("data", [])

    def get_match(self, match_id: int) -> dict[str, Any]:
        return self._get(f"/matches/{match_id}").get("data", {})

    def get_match_events(self, match_id: int) -> list[dict[str, Any]]:
        return self._get(f"/matches/{match_id}/events").get("data", [])

    def get_match_set_pieces(self, match_id: int) -> list[dict[str, Any]]:
        return self._get(f"/matches/{match_id}/set-pieces").get("data", [])

    def get_match_player_kpis(self, match_id: int) -> list[dict[str, Any]]:
        return self._get(f"/matches/{match_id}/player-kpis").get("data", [])

    def get_match_player_scores(self, match_id: int) -> list[dict[str, Any]]:
        return self._get(f"/matches/{match_id}/player-scores").get("data", [])

    def get_match_squad_kpis(self, match_id: int) -> list[dict[str, Any]]:
        return self._get(f"/matches/{match_id}/squad-kpis").get("data", [])

    def get_match_squad_scores(self, match_id: int) -> list[dict[str, Any]]:
        return self._get(f"/matches/{match_id}/squad-scores").get("data", [])

    def get_match_event_kpis(self, match_id: int) -> list[dict[str, Any]]:
        return self._get(f"/matches/{match_id}/event-kpis").get("data", [])

    def get_event_kpi_catalog(self) -> list[dict[str, Any]]:
        return self._get("/kpis/event", {"language": "en"}).get("data", [])

    def get_player_score_catalog(self) -> list[dict[str, Any]]:
        return self._get("/player-scores", {"language": "en"}).get("data", [])

    def get_squad_score_catalog(self) -> list[dict[str, Any]]:
        return self._get("/squad-scores", {"language": "en"}).get("data", [])

    def get_kpi_catalog(self) -> list[dict[str, Any]]:
        return self._get("/kpis", {"language": "en"}).get("data", [])

    def get_match_bundle(self, match_id: int) -> dict[str, Any]:
        match = self.get_match(match_id)
        iteration_id = match.get("iterationId")
        squads = self.get_squads(iteration_id) if iteration_id is not None else []
        iteration_players = self.get_iteration_players(iteration_id) if iteration_id is not None else []
        match_rows = self.get_matches(iteration_id) if iteration_id is not None else []
        match_summary = next((row for row in match_rows if row.get("id") == match_id), {})
        return {
            "match": match,
            "match_summary": match_summary,
            "events": self.get_match_events(match_id),
            "set_pieces": self.get_match_set_pieces(match_id),
            "player_kpis": self.get_match_player_kpis(match_id),
            "player_scores": self.get_match_player_scores(match_id),
            "squad_kpis": self.get_match_squad_kpis(match_id),
            "squad_scores": self.get_match_squad_scores(match_id),
            "kpi_catalog": self.get_kpi_catalog(),
            "player_score_catalog": self.get_player_score_catalog(),
            "squad_score_catalog": self.get_squad_score_catalog(),
            "event_kpis": self.get_match_event_kpis(match_id),
            "event_kpi_catalog": self.get_event_kpi_catalog(),
            "squads": squads,
            "iteration_players": iteration_players,
        }

    @staticmethod
    def save_bundle(bundle: dict[str, Any], folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        for name, payload in bundle.items():
            (folder / f"{name}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
