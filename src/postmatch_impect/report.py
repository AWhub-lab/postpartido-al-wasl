from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PREFERRED_SQUAD_SCORE_NAMES = [
    "RATIO_BALL_POSSESSION",
    "RATIO_PASSING_ACCURACY",
    "RATIO_DUELS",
    "RATIO_GROUND_DUELS",
    "RATIO_AERIAL_DUELS",
    "PXT_POSITIVE",
    "PRESSURE_HEIGHT",
    "FIELD_TILT",
    "EXPECTED_POINTS_SHOT_XG",
    "EXPECTED_POINTS_PACKING_XG",
]

PREFERRED_KPI_NAMES = [
    "GOALS",
    "SHOT_AT_GOAL_NUMBER",
    "SHOT_XG",
    "POSTSHOT_XG",
    "PACKING_XG",
    "PXT_POSITIVE",
    "BYPASSED_OPPONENTS",
    "BYPASSED_DEFENDERS",
]


def _safe_name(item: dict[str, Any] | None, fallback: str) -> str:
    if not item:
        return fallback
    for key in ("name", "commonname", "shortName", "label"):
        value = item.get(key)
        if value:
            return str(value)
    return fallback


def _match_date(match_data: dict[str, Any], match_summary: dict[str, Any]) -> str:
    for source in (match_summary, match_data):
        for key in ("date", "matchDate", "kickoff", "kickOff", "startTime", "dateTime", "scheduledDate"):
            value = source.get(key)
            if value:
                return str(value)
    return "Fecha no disponible"


def _match_datetime_display(match_data: dict[str, Any], match_summary: dict[str, Any]) -> str:
    raw = _match_date(match_data, match_summary)
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return raw


def _matchday_display(match_summary: dict[str, Any], lang: str = "es") -> str:
    match_day = match_summary.get("matchDay") or {}
    index = match_day.get("index")
    if isinstance(index, int):
        label = "Matchday" if lang == "en" else "Jornada"
        return f"{label} {index + 1}"
    name = match_day.get("name")
    return str(name) if name else "-"


def _goals_summary(match_summary: dict[str, Any]) -> tuple[int | None, int | None, int | None, int | None]:
    goals = match_summary.get("goals") or {}
    home = goals.get("home") or {}
    away = goals.get("away") or {}
    return home.get("fullTime"), away.get("fullTime"), home.get("halfTime"), away.get("halfTime")


def _extract_score(match_data: dict[str, Any], match_summary: dict[str, Any]) -> str:
    result = match_summary.get("result")
    if result:
        return str(result)
    goals = match_summary.get("goals")
    if isinstance(goals, dict):
        home = goals.get("home")
        away = goals.get("away")
        if home is not None and away is not None:
            return f"{home}-{away}"
    goals = match_data.get("goals")
    if isinstance(goals, dict):
        home = goals.get("home")
        away = goals.get("away")
        if home is not None and away is not None:
            return f"{home}-{away}"
    return "Marcador no disponible"


def _catalog_maps(rows: list[dict[str, Any]]) -> tuple[dict[int, str], dict[int, str]]:
    name_map: dict[int, str] = {}
    label_map: dict[int, str] = {}
    for row in rows:
        item_id = row.get("id")
        if item_id is None:
            continue
        details = row.get("details") or {}
        name_map[int(item_id)] = str(row.get("name") or item_id)
        label_map[int(item_id)] = str(details.get("label") or row.get("name") or item_id)
    return name_map, label_map


def _squads_by_id(bundle: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(row["id"]): row for row in bundle.get("squads", []) if row.get("id") is not None}


def _players_by_id(bundle: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(row["id"]): row for row in bundle.get("iteration_players", []) if row.get("id") is not None}


def _player_name(player: dict[str, Any] | None, fallback_id: int | None = None) -> str:
    if not player:
        return f"Player {fallback_id}" if fallback_id is not None else "Player"
    for key in ("commonname", "name", "shortName"):
        value = player.get(key)
        if value:
            return str(value)
    first = player.get("firstname")
    last = player.get("lastname")
    if first or last:
        return " ".join(part for part in [first, last] if part)
    return f"Player {fallback_id}" if fallback_id is not None else "Player"


def _squad_name(squad_id: int | None, bundle: dict[str, Any], fallback: str) -> str:
    if squad_id is None:
        return fallback
    squad = _squads_by_id(bundle).get(int(squad_id))
    return _safe_name(squad, fallback)


def _home_away_meta(bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    match = bundle.get("match", {})
    home_id = (match.get("squadHome") or {}).get("id")
    away_id = (match.get("squadAway") or {}).get("id")
    return (
        {"id": home_id, "name": _squad_name(home_id, bundle, "Home")},
        {"id": away_id, "name": _squad_name(away_id, bundle, "Away")},
    )


def _is_al_wasl(name: str | None) -> bool:
    return "wasl" in (name or "").lower()


def _al_wasl_and_rival_meta(bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    home_meta, away_meta = _home_away_meta(bundle)
    if _is_al_wasl(home_meta["name"]):
        return home_meta, away_meta
    return away_meta, home_meta


def _event_shot_xg_map(bundle: dict[str, Any]) -> dict[int, float]:
    catalog = bundle.get("event_kpi_catalog", []) or []
    shot_xg_kpi_id = next((row.get("id") for row in catalog if row.get("name") == "SHOT_XG"), None)
    if shot_xg_kpi_id is None:
        return {}
    values: dict[int, float] = {}
    for row in bundle.get("event_kpis", []) or []:
        if row.get("kpiId") != shot_xg_kpi_id:
            continue
        event_id = row.get("eventId")
        value = row.get("value")
        if event_id is not None and isinstance(value, (int, float)):
            values[int(event_id)] = float(value)
    return values


def _flatten_player_scores(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    score_names, score_labels = _catalog_maps(bundle.get("player_score_catalog", []))
    players_by_id = _players_by_id(bundle)
    payload = bundle.get("player_scores", {}) or {}
    rows: list[dict[str, Any]] = []
    for side in ("squadHome", "squadAway"):
        squad_block = payload.get(side) or {}
        squad_id = squad_block.get("id")
        squad_name = _squad_name(squad_id, bundle, f"Squad {squad_id or '?'}")
        for player_block in squad_block.get("players", []):
            player_id = player_block.get("id")
            player_meta = players_by_id.get(int(player_id)) if player_id is not None and int(player_id) in players_by_id else None
            player_name = _player_name(player_meta, player_id)
            total_value = 0.0
            for score in player_block.get("playerScores", []):
                value = score.get("value")
                score_id = score.get("playerScoreId")
                if isinstance(value, (int, float)):
                    total_value += float(value)
                rows.append(
                    {
                        "player_name": player_name,
                        "player_id": player_id,
                        "squad_id": squad_id,
                        "squad_name": squad_name,
                        "position": player_block.get("position"),
                        "play_duration": player_block.get("playDuration"),
                        "match_share": player_block.get("matchShare"),
                        "score_id": score_id,
                        "score_name": score_names.get(score_id, str(score_id)),
                        "score_label": score_labels.get(score_id, str(score_id)),
                        "value": value,
                    }
                )
            rows.append(
                {
                    "player_name": player_name,
                    "player_id": player_id,
                    "squad_id": squad_id,
                    "squad_name": squad_name,
                    "position": player_block.get("position"),
                    "play_duration": player_block.get("playDuration"),
                    "match_share": player_block.get("matchShare"),
                    "score_id": "__aggregate__",
                    "score_name": "AGGREGATE_SUM",
                    "score_label": "Aggregate score sum",
                    "value": round(total_value, 3),
                }
            )
    return rows


def _compare_squad_scores(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    score_names, score_labels = _catalog_maps(bundle.get("squad_score_catalog", []))
    payload = bundle.get("squad_scores", {}) or {}
    home_meta, away_meta = _home_away_meta(bundle)
    comparison: list[dict[str, Any]] = []
    home_scores = {row["squadScoreId"]: row["value"] for row in (payload.get("squadHome") or {}).get("squadScores", [])}
    away_scores = {row["squadScoreId"]: row["value"] for row in (payload.get("squadAway") or {}).get("squadScores", [])}
    for score_id in sorted(set(home_scores) | set(away_scores)):
        name = score_names.get(score_id, str(score_id))
        if name not in PREFERRED_SQUAD_SCORE_NAMES:
            continue
        home_value = home_scores.get(score_id)
        away_value = away_scores.get(score_id)
        if isinstance(home_value, (int, float)) and isinstance(away_value, (int, float)):
            edge = home_meta["name"] if home_value > away_value else away_meta["name"] if away_value > home_value else "Empate"
        else:
            edge = "-"
        comparison.append(
            {
                "metric": score_labels.get(score_id, name),
                "metric_name": name,
                "home": home_value,
                "away": away_value,
                "edge": edge,
            }
        )
    return comparison


def _compare_squad_kpis(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    kpi_names, kpi_labels = _catalog_maps(bundle.get("kpi_catalog", []))
    payload = bundle.get("squad_kpis", {}) or {}
    home_meta, away_meta = _home_away_meta(bundle)
    comparison: list[dict[str, Any]] = []
    home_kpis = {row["kpiId"]: row["value"] for row in (payload.get("squadHome") or {}).get("kpis", [])}
    away_kpis = {row["kpiId"]: row["value"] for row in (payload.get("squadAway") or {}).get("kpis", [])}
    for kpi_id in sorted(set(home_kpis) | set(away_kpis)):
        name = kpi_names.get(kpi_id, str(kpi_id))
        if name not in PREFERRED_KPI_NAMES:
            continue
        home_value = home_kpis.get(kpi_id)
        away_value = away_kpis.get(kpi_id)
        if isinstance(home_value, (int, float)) and isinstance(away_value, (int, float)):
            edge = home_meta["name"] if home_value > away_value else away_meta["name"] if away_value > home_value else "Empate"
        else:
            edge = "-"
        comparison.append(
            {
                "metric": kpi_labels.get(kpi_id, name),
                "metric_name": name,
                "home": home_value,
                "away": away_value,
                "edge": edge,
            }
        )
    return comparison


def _event_team_summary(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    home_meta, away_meta = _home_away_meta(bundle)
    team_names = {home_meta["id"]: home_meta["name"], away_meta["id"]: away_meta["name"]}
    counters: dict[int, dict[str, Any]] = defaultdict(lambda: {"passes": 0, "completed_passes": 0, "shots": 0, "goals": 0})
    for event in bundle.get("events", []):
        squad_id = event.get("squadId")
        if squad_id not in team_names:
            continue
        if event.get("pass"):
            counters[squad_id]["passes"] += 1
            if event.get("result") == "SUCCESS":
                counters[squad_id]["completed_passes"] += 1
        if event.get("shot"):
            counters[squad_id]["shots"] += 1
            if event.get("result") == "SUCCESS":
                counters[squad_id]["goals"] += 1
    rows = []
    for squad_id, name in team_names.items():
        row = counters[squad_id]
        passes = row["passes"]
        completed = row["completed_passes"]
        rows.append(
            {
                "team": name,
                "passes": passes,
                "completed_passes": completed,
                "pass_accuracy": round(completed / passes, 3) if passes else None,
                "shots": row["shots"],
                "goals_from_events": row["goals"],
            }
        )
    return rows


def _top_passing_links(bundle: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    players_by_id = _players_by_id(bundle)
    team_lookup = {}
    for meta in ("squadHome", "squadAway"):
        squad = (bundle.get("match") or {}).get(meta) or {}
        team_lookup[squad.get("id")] = _squad_name(squad.get("id"), bundle, meta)
    link_counter: Counter[tuple[int, int, int]] = Counter()
    for event in bundle.get("events", []):
        if not event.get("pass") or event.get("result") != "SUCCESS":
            continue
        squad_id = event.get("squadId")
        passer_id = (event.get("player") or {}).get("id")
        receiver_id = ((event.get("pass") or {}).get("receiver") or {}).get("playerId")
        receiver_type = ((event.get("pass") or {}).get("receiver") or {}).get("type")
        if not passer_id or not receiver_id or receiver_type != "TEAMMATE":
            continue
        link_counter[(squad_id, passer_id, receiver_id)] += 1
    rows = []
    for (squad_id, passer_id, receiver_id), value in link_counter.most_common(limit):
        rows.append(
            {
                "team": team_lookup.get(squad_id, f"Squad {squad_id}"),
                "passer": _player_name(players_by_id.get(passer_id), passer_id),
                "receiver": _player_name(players_by_id.get(receiver_id), receiver_id),
                "count": value,
            }
        )
    return rows


def _top_passers(bundle: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    players_by_id = _players_by_id(bundle)
    team_lookup = {}
    for meta in ("squadHome", "squadAway"):
        squad = (bundle.get("match") or {}).get(meta) or {}
        team_lookup[squad.get("id")] = _squad_name(squad.get("id"), bundle, meta)
    counts: Counter[tuple[int, int]] = Counter()
    for event in bundle.get("events", []):
        if event.get("pass") and event.get("result") == "SUCCESS":
            squad_id = event.get("squadId")
            player_id = (event.get("player") or {}).get("id")
            if squad_id and player_id:
                counts[(squad_id, player_id)] += 1
    rows = []
    for (squad_id, player_id), value in counts.most_common(limit):
        rows.append(
            {
                "team": team_lookup.get(squad_id, f"Squad {squad_id}"),
                "player": _player_name(players_by_id.get(player_id), player_id),
                "completed_passes": value,
            }
        )
    return rows


def _shot_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    players_by_id = _players_by_id(bundle)
    team_lookup = {}
    for meta in ("squadHome", "squadAway"):
        squad = (bundle.get("match") or {}).get(meta) or {}
        team_lookup[squad.get("id")] = _squad_name(squad.get("id"), bundle, meta)
    rows = []
    for event in bundle.get("events", []):
        if not event.get("shot"):
            continue
        player_id = (event.get("player") or {}).get("id")
        squad_id = event.get("squadId")
        start = event.get("start") or {}
        rows.append(
            {
                "time": ((event.get("gameTime") or {}).get("gameTime") or "?"),
                "team": team_lookup.get(squad_id, f"Squad {squad_id}"),
                "player": _player_name(players_by_id.get(player_id), player_id),
                "action": event.get("action"),
                "result": event.get("result"),
                "distance": (event.get("shot") or {}).get("distance"),
                "lane": start.get("lane"),
                "phase": event.get("phase"),
            }
        )
    return rows


def _set_piece_summary(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    home_meta, away_meta = _home_away_meta(bundle)
    team_lookup = {home_meta["id"]: home_meta["name"], away_meta["id"]: away_meta["name"]}
    grouped: dict[tuple[int, str], dict[str, float]] = defaultdict(lambda: {"count": 0, "shot_xg": 0.0, "goals": 0.0, "pxt_positive": 0.0})
    for row in bundle.get("set_pieces", []):
        squad_id = row.get("squadId")
        category = row.get("adjSetPieceCategory") or row.get("setPieceCategory") or "UNKNOWN"
        key = (squad_id, category)
        grouped[key]["count"] += 1
        for sub_phase in row.get("setPieceSubPhase") or []:
            aggregates = sub_phase.get("aggregates") or {}
            grouped[key]["shot_xg"] += float(aggregates.get("SHOT_XG") or 0.0)
            grouped[key]["goals"] += float(aggregates.get("GOALS") or 0.0)
            grouped[key]["pxt_positive"] += float(aggregates.get("PXT_POSITIVE") or 0.0)
    rows = []
    for (squad_id, category), values in grouped.items():
        rows.append(
            {
                "team": team_lookup.get(squad_id, f"Squad {squad_id}"),
                "category": category,
                "count": int(values["count"]),
                "shot_xg": round(values["shot_xg"], 3),
                "goals": round(values["goals"], 3),
                "pxt_positive": round(values["pxt_positive"], 3),
            }
        )
    rows.sort(key=lambda row: (row["team"], -row["count"], -row["shot_xg"]))
    return rows


def _fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if value is None:
        return "-"
    return str(value)


def build_markdown_report(match_id: int, bundle: dict[str, Any]) -> str:
    match_data = bundle.get("match", {})
    match_summary = bundle.get("match_summary", {})
    home_meta, away_meta = _home_away_meta(bundle)
    home = home_meta["name"]
    away = away_meta["name"]
    date_text = _match_date(match_data, match_summary)
    score_text = _extract_score(match_data, match_summary)
    event_count = len(bundle.get("events", []))
    set_piece_count = len(bundle.get("set_pieces", []))

    player_scores = _flatten_player_scores(bundle)
    squad_score_rows = _compare_squad_scores(bundle)
    squad_kpi_rows = _compare_squad_kpis(bundle)
    event_summary = _event_team_summary(bundle)
    top_players = sorted(
        [row for row in player_scores if row["score_id"] == "__aggregate__" and isinstance(row["value"], (int, float))],
        key=lambda row: row["value"],
        reverse=True,
    )[:12]
    top_passers = _top_passers(bundle)
    top_links = _top_passing_links(bundle)
    shot_rows = _shot_rows(bundle)
    set_piece_rows = _set_piece_summary(bundle)[:12]

    lines = [
        f"# Informe postpartido IMPECT: {home} vs {away}",
        "",
        f"- Match ID: `{match_id}`",
        f"- Fecha: `{date_text}`",
        f"- Marcador: `{score_text}`",
        f"- Eventos descargados: `{event_count}`",
        f"- Jugadas a balón parado detectadas: `{set_piece_count}`",
        "",
        "## Resumen ejecutivo",
        "",
        f"Informe generado con datos match-level de IMPECT para **{home}** y **{away}**. El objetivo de esta versión es dejar un postpartido funcional y repetible a partir de los endpoints reales de partido.",
        "",
        "## Resumen de juego por equipo",
        "",
        "| Equipo | Pases | Pases completados | Precisión pase | Tiros | Goles detectados en eventos |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in event_summary:
        lines.append(
            f"| {row['team']} | {_fmt(row['passes'], 0)} | {_fmt(row['completed_passes'], 0)} | {_fmt(row['pass_accuracy'])} | "
            f"{_fmt(row['shots'], 0)} | {_fmt(row['goals_from_events'], 0)} |"
        )

    lines.extend(
        [
            "",
            "## Comparativa equipo vs rival: squad scores",
            "",
            "| Métrica | Home | Away | Ventaja |",
            "|---|---:|---:|---|",
        ]
    )
    for row in squad_score_rows:
        lines.append(f"| {row['metric']} | {_fmt(row['home'])} | {_fmt(row['away'])} | {row['edge']} |")

    lines.extend(
        [
            "",
            "## Comparativa equipo vs rival: KPIs de partido",
            "",
            "| Métrica | Home | Away | Ventaja |",
            "|---|---:|---:|---|",
        ]
    )
    for row in squad_kpi_rows:
        lines.append(f"| {row['metric']} | {_fmt(row['home'])} | {_fmt(row['away'])} | {row['edge']} |")

    lines.extend(
        [
            "",
            "## Top jugadores por suma agregada de scores",
            "",
            "| Jugador | Equipo | Posición | Minutos | Match share | Suma scores |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for row in top_players:
        lines.append(
            f"| {row['player_name']} | {row['squad_name']} | {row.get('position') or '-'} | "
            f"{_fmt(row.get('play_duration'))} | {_fmt(row.get('match_share'))} | {_fmt(row['value'])} |"
        )

    lines.extend(
        [
            "",
            "## Juego de pase",
            "",
            "### Máximos pasadores",
            "",
            "| Jugador | Equipo | Pases completados |",
            "|---|---|---:|",
        ]
    )
    for row in top_passers:
        lines.append(f"| {row['player']} | {row['team']} | {_fmt(row['completed_passes'], 0)} |")

    lines.extend(
        [
            "",
            "### Conexiones de pase más repetidas",
            "",
            "| Equipo | Pasador | Receptor | Conexiones |",
            "|---|---|---|---:|",
        ]
    )
    for row in top_links:
        lines.append(f"| {row['team']} | {row['passer']} | {row['receiver']} | {_fmt(row['count'], 0)} |")

    lines.extend(
        [
            "",
            "## Tiros y finalizaciones",
            "",
            "| Tiempo | Equipo | Jugador | Acción | Resultado | Distancia | Calle | Fase |",
            "|---|---|---|---|---|---:|---|---|",
        ]
    )
    for row in shot_rows[:20]:
        lines.append(
            f"| {row['time']} | {row['team']} | {row['player']} | {row.get('action') or '-'} | {row.get('result') or '-'} | "
            f"{_fmt(row.get('distance'))} | {row.get('lane') or '-'} | {row.get('phase') or '-'} |"
        )

    lines.extend(
        [
            "",
            "## Balón parado",
            "",
            "| Equipo | Tipo | Acciones | Shot xG | Goles | PxT positivo |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in set_piece_rows:
        lines.append(
            f"| {row['team']} | {row['category']} | {_fmt(row['count'], 0)} | {_fmt(row['shot_xg'])} | "
            f"{_fmt(row['goals'])} | {_fmt(row['pxt_positive'])} |"
        )

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.extend(
        [
            "",
            "## Próximas mejoras sugeridas",
            "",
            "- Añadir visual de red de pases en imagen",
            "- Añadir mapa de tiros con coordenadas",
            "- Añadir bloque automático de conclusiones por equipo",
            "- Añadir monitor de disponibilidad para nuevos partidos",
            "",
            f"_Generado localmente el {generated}_",
        ]
    )
    return "\n".join(lines)


def write_markdown_report(match_id: int, content: str, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"match_{match_id}_report.md"
    report_path.write_text(content, encoding="utf-8")
    return report_path
