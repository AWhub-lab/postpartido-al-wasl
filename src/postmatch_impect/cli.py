from __future__ import annotations

import argparse
from typing import Any

from .bundle import load_local_bundle
from .client import ImpectClient
from .config import ROOT, get_settings
from .pdf_report import render_pdf_report
from .report import build_markdown_report, write_markdown_report


def _safe_team_name(match_row: dict[str, Any], side: str, squads_by_id: dict[int, dict[str, Any]] | None = None) -> str:
    candidates = [
        match_row.get(side, {}),
        match_row.get(f"{side}Squad", {}),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ("name", "shortName", "commonname"):
                value = candidate.get(key)
                if value:
                    return str(value)
    for key in (f"{side}Name", f"{side}_name"):
        value = match_row.get(key)
        if value:
            return str(value)
    squad_id = match_row.get(f"{side}SquadId")
    if squads_by_id and squad_id in squads_by_id:
        squad = squads_by_id[squad_id]
        for key in ("name", "shortName", "commonname"):
            value = squad.get(key)
            if value:
                return str(value)
    return side.title()


def _iteration_competition_name(row: dict[str, Any]) -> str:
    competition = row.get("competition") or {}
    return str(competition.get("name") or row.get("competitionName") or "-")


def _iteration_season(row: dict[str, Any]) -> str:
    return str(row.get("season") or "-")


def _match_is_available(row: dict[str, Any]) -> bool:
    return bool(row.get("available"))


def _match_date(row: dict[str, Any]) -> str:
    return str(
        row.get("date")
        or row.get("matchDate")
        or row.get("scheduledDate")
        or row.get("kickoff")
        or "?"
    )


def cmd_list_iterations(args: argparse.Namespace) -> int:
    client = ImpectClient(get_settings())
    rows = client.get_iterations()
    if args.season:
        rows = [row for row in rows if _iteration_season(row) == args.season]
    if args.competition:
        needle = args.competition.lower()
        rows = [row for row in rows if needle in _iteration_competition_name(row).lower()]
    rows = sorted(
        rows,
        key=lambda row: (_iteration_competition_name(row).lower(), _iteration_season(row)),
        reverse=False,
    )
    for row in rows:
        print(f"{row.get('id')} | {_iteration_competition_name(row)} | season={_iteration_season(row)}")
    return 0


def cmd_list_matches(args: argparse.Namespace) -> int:
    client = ImpectClient(get_settings())
    rows = client.get_matches(args.iteration_id)
    squads = client.get_squads(args.iteration_id)
    squads_by_id = {int(row["id"]): row for row in squads if row.get("id") is not None}
    if args.team:
        needle = args.team.lower()
        rows = [
            row for row in rows
            if needle in _safe_team_name(row, "home", squads_by_id).lower()
            or needle in _safe_team_name(row, "away", squads_by_id).lower()
        ]

    if args.available_only:
        rows = [row for row in rows if _match_is_available(row)]

    rows = sorted(rows, key=lambda row: _match_date(row))
    for row in rows:
        home = _safe_team_name(row, "home", squads_by_id)
        away = _safe_team_name(row, "away", squads_by_id)
        available = row.get("available")
        date_text = _match_date(row)
        print(f"{row.get('id')} | {date_text} | {home} vs {away} | available={available}")
    return 0


def _langs_for(value: str) -> list[str]:
    return ["es", "en"] if value == "both" else [value]


def cmd_report(args: argparse.Namespace) -> int:
    client = ImpectClient(get_settings())
    bundle = client.get_match_bundle(args.match_id)

    raw_dir = ROOT / "data" / "raw" / f"match_{args.match_id}"
    reports_dir = ROOT / "reports"
    client.save_bundle(bundle, raw_dir)

    markdown = build_markdown_report(args.match_id, bundle)
    report_path = write_markdown_report(args.match_id, markdown, reports_dir)
    print(f"Crudo guardado en: {raw_dir}")
    print(f"Informe generado en: {report_path}")
    for lang in _langs_for(args.lang):
        pdf_path = render_pdf_report(args.match_id, bundle, lang)
        print(f"PDF generado en ({lang}): {pdf_path}")
    return 0


def cmd_render_local(args: argparse.Namespace) -> int:
    bundle = load_local_bundle(args.match_id)
    reports_dir = ROOT / "reports"
    markdown = build_markdown_report(args.match_id, bundle)
    report_path = write_markdown_report(args.match_id, markdown, reports_dir)
    print(f"Informe regenerado en: {report_path}")
    for lang in _langs_for(args.lang):
        pdf_path = render_pdf_report(args.match_id, bundle, lang)
        print(f"PDF regenerado en ({lang}): {pdf_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Herramientas postpartido IMPECT")
    subparsers = parser.add_subparsers(dest="command", required=True)

    iterations_parser = subparsers.add_parser("list-iterations", help="Lista iteraciones/temporadas IMPECT")
    iterations_parser.add_argument("--season", help="Filtro exacto de temporada, por ejemplo 26/27")
    iterations_parser.add_argument("--competition", help="Filtro por nombre de competicion")
    iterations_parser.set_defaults(func=cmd_list_iterations)

    matches_parser = subparsers.add_parser("list-matches", help="Lista partidos de una iteration IMPECT")
    matches_parser.add_argument("--iteration-id", type=int, required=True)
    matches_parser.add_argument("--team", help="Filtro opcional por nombre de equipo")
    matches_parser.add_argument("--available-only", action="store_true", help="Mostrar solo partidos disponibles")
    matches_parser.set_defaults(func=cmd_list_matches)

    report_parser = subparsers.add_parser("report", help="Descarga un partido y genera un informe Markdown")
    report_parser.add_argument("--match-id", type=int, required=True)
    report_parser.add_argument("--lang", choices=["es", "en", "both"], default="es", help="Idioma del PDF (por defecto es)")
    report_parser.set_defaults(func=cmd_report)

    render_parser = subparsers.add_parser("render-local", help="Regenera Markdown y PDF desde un bundle ya descargado")
    render_parser.add_argument("--match-id", type=int, required=True)
    render_parser.add_argument("--lang", choices=["es", "en", "both"], default="es", help="Idioma del PDF (por defecto es)")
    render_parser.set_defaults(func=cmd_render_local)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
